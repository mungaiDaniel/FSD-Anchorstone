# 03 — General ledger

This document designs a double-entry general ledger (GL) that both businesses post into, and a safe path for moving today's investor ledger onto it.

**The rules from `CLAUDE.md` still hold:**
- Money is `Decimal` / `NUMERIC(20,2)`.
- "Today" means Nairobi time.
- Posted records are immutable; corrections are reversals.
- Maker-checker applies.
- Everything is audited in the same transaction.
- **One module owns balance logic.**

---

## ADR-03-1 — Build the GL inside the system

**Context.** The FSD wants integrated, real-time accounting:
- subledgers for facilities, deposits, payables and receivables;
- drill-down from the trial balance to the transaction;
- branch trial balances;
- every posting tagged to a loan or member number.

Anchorstone has no accounting system connected today.

**Options considered**

| Option | Assessment |
|---|---|
| A. Export journals to an external package (QuickBooks, Xero, Sage, ERPNext) | Less to build for statutory accounts. But two systems of record, no real-time subledger, reconciliation every day, and the FSD's drill-down and branch TB requirements end up split across products. |
| B. **Own GL in PostgreSQL**, with exports for auditors and tax | One source of truth. The subledger is the GL. Database-enforced invariants. |

**Decision.** **Option B.** The GL lives in a new `app/Ledger` module. Finance can still export the trial balance and journals to a package for statutory reporting if they want (Q-F9).

**Consequences**
- We own correctness of double entry. Hence the DB-level constraints below, and a big reconciliation test suite.
- Report building (TB, BS, P&L) is in scope (phase 11).

## ADR-03-2 — Balanced entries enforced by the database, not just code

**Context.** A bug in any posting path must not be able to save an unbalanced journal.

| Option | Assessment |
|---|---|
| A. Check only in Python before insert | Bypassable by any other code path, bulk script or migration. |
| B. Store the debit total and credit total on the entry header, with a CHECK that they're equal | Doesn't prove the *lines* add up to the header. |
| C. **Deferred constraint trigger on `journal_lines`** that checks Σdebit = Σcredit (and ≥ 2 lines) per entry at COMMIT | Enforced for every writer. Deferred, so lines can be inserted one by one inside a transaction. |

**Decision.** **Option C, plus the Python check** (the Python check gives a readable error, the trigger is the guarantee):

```sql
CREATE FUNCTION gl_assert_entry_balanced() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE e_id bigint := COALESCE(NEW.entry_id, OLD.entry_id);
        d numeric; c numeric; n int;
BEGIN
  SELECT COALESCE(SUM(debit),0), COALESCE(SUM(credit),0), COUNT(*)
    INTO d, c, n FROM journal_lines WHERE entry_id = e_id;
  IF n < 2 OR d <> c OR d = 0 THEN
    RAISE EXCEPTION 'Journal entry % is unbalanced (debits %, credits %, lines %)', e_id, d, c, n;
  END IF;
  RETURN NULL;
END $$;

CREATE CONSTRAINT TRIGGER trg_journal_balanced
  AFTER INSERT ON journal_lines
  DEFERRABLE INITIALLY DEFERRED
  FOR EACH ROW EXECUTE FUNCTION gl_assert_entry_balanced();
```

Supporting constraints:
- **Line shape:** `CHECK ((debit > 0 AND credit = 0) OR (credit > 0 AND debit = 0))`, both `NUMERIC(20,2)`.
- **Header without lines is invalid:** a deferred trigger on `journal_entries` INSERT asserts the entry has lines at commit.
- **Currency:** `journal_lines.currency` must equal `journal_entries.currency`, via a composite FK `(entry_id, currency)` → `journal_entries(id, currency)`.
- **Control accounts:** a line on a GL account with `is_control = true` must carry `account_id`, and that account's `gl_control_account_id` must equal the line's GL account (trigger). A line on a non-control account must **not** carry `account_id`.

**Consequences**
- Tests that insert unbalanced data must expect failure at commit. The existing test-suite pattern (one transaction per request) works unchanged.

## ADR-03-3 — Immutability: reversal only

**Decision.**
- `journal_entries` and `journal_lines` have a `BEFORE UPDATE OR DELETE` trigger that raises. There are no exceptions; the reversal link lives on the *new* row, so nothing is ever updated.
- The application's DB role also lacks UPDATE/DELETE grants on these tables (defence in depth). Migrations run as the owner role.
- **Reversal.** A new entry has `reverses_entry_id` (unique) pointing at the original, and its lines mirror the original's with debit and credit swapped. "Is reversed" means a row exists with `reverses_entry_id = X`. A reversal of a reversal is refused.
- **Dating of reversals.** The reversal's `business_date` is **the original's business date** when that date is still in an open GL period (today's rule: a deposit reversal removes it as if it never happened, which interest and statements rely on). Otherwise it's today, with an explicit `reason`. See §7.3 for why this matters for the backfill.
- **Period control.** A `BEFORE INSERT` trigger refuses entries whose `business_date` falls in a `closed` `gl_periods` row. Today's `assert_not_locked()` becomes a call to the same rule.

**Consequences**
- Mistakes in a closed month are corrected in the current month. That's standard practice, and consistent with today's "approved interest months are locked".
- `audit_logs` should get the same trigger (04, phase 12).

## ADR-03-4 — Balances are derived from GL lines; one module computes them

**Context.**
- Today `app/Transactions/ledger.py` is the only place that defines an investor's balance (posted deposits − approved withdrawals by value date).
- Interest, statements, the overview, reports and withdrawal checks all call it.

**Options considered**

| Option | Assessment |
|---|---|
| A. Running balance column on `accounts` updated on every post | Fast, but a second source of truth that can drift. Needs row locks on hot accounts. |
| B. **Always aggregate `journal_lines`** (indexed by `(account_id, business_date)`), with optional end-of-day snapshots (`account_balance_snapshots`, written by EOD and *verifiable* from lines) for speed | One source of truth. Snapshots are a cache that can be rebuilt from lines at any time. |

**Decision.** **Option B.**
- `ledger.py` keeps its public functions:
  - `balance_as_of`, `balance_events`, `min_balance_from`, `investor_totals`, `balances_subquery`, `ledger_entries`, `lock_investor`, `assert_not_locked`;
  - plus new `account_balance`, `available_balance` (balance − active holds), `lock_account`.
- Behind them, the source switches from deposit/withdrawal tables to GL lines (§7.5).
- In phase 4 it moves to `app/Ledger/balances.py`, and `app/Transactions/ledger.py` becomes a thin re-export so imports don't break. **No other module may sum journal lines.** A unit test greps for `func.sum(JournalLine` outside `app/Ledger/` and fails if it finds one.

**Consequences**
- Investor interest (`compute_payouts`) keeps working unchanged. It consumes `balance_events()`, which will yield the same `(date, signed amount)` pairs from GL lines.
- Snapshot correctness is part of the EOD checks.

## ADR-03-5 — Posting engine: events and rules, not free-form journals

**Context.**
- The FSD lists, per product, the Dr/Cr pairs for every event.
- They're nearly identical across products and differ only in which GL account the product maps to.

**Decision.**
- Business code never builds journal lines. It calls `ledger.post(event_code, source, amounts, context)`.
- The engine looks up the **posting rule** for `(event_code, product_kind)`, resolves account *roles* through `product_gl_mappings` (02 §1.4) and fixed system accounts, and writes one balanced entry.
- **Idempotency.** `journal_entries` has a unique `(source_type, source_id, event_code, occurrence)`, so a retried request or job can't post twice.
- **Rules** are versioned **data** (`gl_posting_rules` + `gl_posting_rule_lines`: account, debit or credit, amount field, client-account reference), insert-only in the database. A new version is a `gl.posting_rule.change` change request (second approver), dated today or later; the engine uses the version in force on the event's value date, and each journal records it (`journal_entries.posting_rule_id`). A rule is balanced by construction: every amount field appears on as many debit lines as credit lines. *(Changed from "rules in Python" at the user's decision, 17 Oct 2026.)* **Account mappings** are user-editable through maker-checker too.
- **Events** are recorded in `gl_events` (insert-only), unique on the source key `(event_type, source_type, source_id, occurrence)`: posting the same event twice is refused with a conflict, never duplicated.
- **Manual journals** (finance adjustments) go through `journal_drafts` → maker-checker → post. Control accounts and income accounts can't take manual entries unless the GL account allows it (FSD "restrict manual debits on income GLs").

**Consequences**
- A new product needs mappings, not code.
- A new *kind of event* needs a rule in code, plus tests.

## ADR-03-6 — When investor interest hits the GL

**Context.**
- FSD private-placement accounting accrues interest **daily** (Dr interest expense, Cr interest payable).
- Anchorstone calculates interest **monthly** after month-end, and a second admin approves it. Until approval, the figures can change if backdated transactions arrive.

**Options considered**

| Option | Assessment |
|---|---|
| A. Daily accrual journals from the live balance | Matches the FSD. But accruals posted before approval would be wrong whenever a backdated deposit lands, and would then need reversing. Creates noise without changing the month-end figure. |
| B. **One accrual journal per approved month, dated the period end** (`business_date = period_end`, posted at approval), one line per investor subledger; payout journals when each payout is marked paid | The GL matches exactly what was approved and what statements show. |
| C. B, plus an estimated month-end accrual that is reversed on approval | Gives accrual-basis management accounts during the gap between month-end and approval, at the cost of two extra journals a month. |

**Decision.** **Option B**, with **C as a finance option** (Q-F5). Corollary: the GL period for month M can't be closed until month M's interest period is approved (EOM checklist, ADR-04-3).

**Consequences.** The P&L shows investor interest expense in the right month once approved. Daily accrual remains available if Anchorstone adopts term placements (Q-M1).

---

### Built in phase 4 (core) — `app/Ledger`

| Piece | Where | Notes |
|---|---|---|
| Chart of accounts | `gl_accounts`, `accounts.py`, `gl.account.create` / `gl.account.change` | Types asset/liability/equity/income/expense (memo accounts not yet), header or postable, control, optional branch, KES. Never deleted (trigger); codes can change. |
| Periods | `gl_periods`, `periods.py`, `gl.period.close` / `gl.period.reopen` | `open` / `closed` only (no `soft_closed` yet). Months close in order after they end; reopen = latest closed only, reason, two super admins. Financial year from `gl.financial_year_end_month`. |
| Journals | `journal_entries`, `journal_lines`, `journals.py` | Triggers in migration `f2a2b3c4d5e6`: balanced at commit, ≥ 2 lines, immutable, closed-period refusal, same-transaction lines, KES composite FK, control/header/inactive/branch checks, gapless `JV-<FY>-000001` numbers allocated by the insert trigger. Reversal link is `reversal_of` (03's `reverses_entry_id`). |
| Engine | `engine.py`, `rules.py`, `gl_events` | `engine.post(event, source=…, value_date=…, branch_id=…, amounts=…, refs=…)`; never commits. Version 1 of the §4.1 investor rules is seeded; the investor services don't call it yet. |
| Balances | `balances.py` (the only module that sums lines) | Account balance (by branch, header roll-up), subledger balance, trial balance, account statement with running balance. |

Not yet built: dual-write from the investor services, backfill and R1–R10 reconciliation (§7), manual journals, `product_gl_mappings` / `company_bank_accounts`, the never-negative backstop (§3.4), snapshots, inter-branch splitting, revoking UPDATE/DELETE grants from the app role, GL screens.

## 1. Tables (summary; full fields in 02 §1.10)

| Table | Purpose | Mutable? |
|---|---|---|
| `gl_accounts` | Chart of accounts (tree) | Yes, via maker-checker. Never deleted once used. |
| `gl_periods` | Monthly periods: open / soft_closed / closed | Status only, via EOM close. |
| `journal_entries` | Header | **No.** |
| `journal_lines` | Lines with branch, subledger account, product and cost-centre dimensions | **No.** |
| `journal_drafts` / `journal_draft_lines` | Manual journals before approval | Yes, until approved. |
| `gl_posting_rules` / `gl_posting_rule_lines` | Event → line templates, versioned | Insert-only; new versions via maker-checker. |
| `product_gl_mappings` | Role → GL account per product version | Via maker-checker. |
| `company_bank_accounts` | Anchorstone's bank accounts and M-Pesa paybill → GL account | Via maker-checker. |
| `account_balance_snapshots` | Optional EOD cache `(account_id, business_date, balance)` | Rebuilt by EOD. Verified against lines. |

Indexes: `journal_lines (account_id, entry_id)`, `journal_lines (gl_account_id, branch_id)`, `journal_entries (business_date)`, `journal_entries (source_type, source_id)`.

## 2. Chart of accounts (skeleton)

Finance owns the real chart (Q-F1). The skeleton below gives every posting rule an account to use and is seeded at phase 4. Codes are illustrative.

| Code | Name | Class | Notes |
|---|---|---|---|
| **1000–1999** | **Assets** | | |
| 1100 | Bank – operating (one child per bank account) | Asset | Mapped from `company_bank_accounts`. |
| 1110 | M-Pesa paybill float | Asset | |
| 1120 | Cheques in clearing | Asset | |
| 1130 | Cash on hand (per branch) | Asset | |
| 1200 | Loans and advances – control (children per product family) | Asset, control | Subledger = loan accounts. |
| 1210 | Interest receivable – control | Asset, control | Subledger = loan accounts. |
| 1211 | Interest in suspense | **Contra-asset** (credit) | FSD "Interest Suspense GL". Netted against 1210 in the balance sheet. |
| 1220 | Penalty receivable – control | Asset, control | |
| 1221 | Penalty in suspense | Contra-asset | |
| 1230 | Fees and charges receivable – control | Asset, control | |
| 1290 | Allowance for impairment (provisions) | Contra-asset | |
| 1300 | Inter-branch – due from (per branch pair) | Asset | Auto-generated. |
| 1400 | Prepayments | Asset | |
| 1500 / 1510 | Fixed assets at cost / accumulated depreciation | Asset / contra | Per category. |
| 1600 | Treasury bills and bonds (FVPL / HTM children), accrued interest purchased, discount/premium | Asset | |
| **2000–2999** | **Liabilities** | | |
| 2100 | **Investor funds – control** | Liability, control | Subledger = investment accounts (`ACL-…`). The investor "balance" today. |
| 2110 | Interest payable to investors – control | Liability, control | Approved, not yet paid. |
| 2120 | Withholding tax payable – investor interest | Liability | 0% at launch. |
| 2200 | Member collection accounts – control | Liability, control | Subledger = borrower MCAs. |
| 2210 | Unallocated receipts (suspense) | Liability | Unmatched M-Pesa / bank receipts. |
| 2300 | Pass-through payables (tracking provider, risk fund, insurers – "MCA subsidiary payable") | Liability | FSD "settlement GLs" (C-5). |
| 2400 / 2410 / 2420 | Borrowings / interest payable on borrowings / WHT payable on borrowing interest | Liability | |
| 2500 | Trade-finance cash margins – control | Liability, control | Subledger = `tf_margin` accounts. |
| 2600 | Inter-branch – due to | Liability | Auto-generated. |
| 2700 / 2710 | Commissions payable / WHT on commissions | Liability | |
| 2800 | Other payables and accruals | Liability | |
| **3000–3999** | **Equity** (share capital, retained earnings, current-year profit) | Equity | Year-end close moves P&L to retained earnings. |
| **4000–4999** | **Income** | | |
| 4100 | Interest income (children per product) | Income | |
| 4200 | Penalty income | Income | |
| 4300 | Fee income (LAF, membership, CRB commission, legal stamp, search, restructure, review …) | Income | Per `fee_definitions.gl_account_id`. |
| 4400 | Guarantee commission income | Income | |
| 4500 | Recoveries of written-off loans | Income | |
| 4600 | Treasury income (T-bill/bond interest, realised gains) | Income | |
| 4700 | FX gains (realised / unrealised) | Income | Disabled at launch. |
| **5000–5999** | **Expenses** | | |
| 5100 | Interest expense – investors | Expense | |
| 5110 | Interest expense – borrowings | Expense | |
| 5200 | Impairment (provision) expense | Expense | |
| 5210 | Loans written off (excess over allowance) | Expense | |
| 5300 | Commission expense | Expense | |
| 5400 | Depreciation | Expense | |
| 5500 | FX losses | Expense | |
| **9000–9999** | **Memorandum (off-balance-sheet)** | Memo | Contingent liabilities on guarantees, and their contra. Excluded from BS/P&L but balanced. |

## 3. How it fits together

### 3.1 Posting call

```python
ledger.post(
    event="LOAN_DISBURSED",
    source=("disbursement_request", req.id),
    business_date=today_eat(),
    branch_id=loan.branch_id,
    amounts={"principal": Decimal("500000.00"), "fees": {...}, "net_payout": Decimal("472800.00")},
    accounts={"loan": loan.account_id, "mca": mca.account_id, "bank": bank.id},
    product_version_id=loan.product_version_id,
)
```

It runs inside the caller's transaction, followed by `create_audit_log(...)`, then `db.session.commit()` (the `CLAUDE.md` pattern).

### 3.2 Line resolution

1. Load the rule for `(event, product_kind)`.
2. Resolve each role (e.g. `loan_principal`) to a GL account via `product_gl_mappings`. System roles (`bank`, `suspense`, `wht_payable`) come from `company_bank_accounts` and system settings.
3. Attach subledger `account_id`s for control accounts.
4. Split across branches if needed (§4.4).
5. Validate in Python: balanced, non-zero, open period. Then insert. The DB trigger re-validates at commit.

### 3.3 Locking

- `lock_account(account_id)` takes `SELECT … FOR UPDATE` on the `accounts` row. It's the generalised `lock_investor`.
- Every posting that can push a non-loan account down takes the lock first, then checks `available_balance`. This is today's withdrawal rule.

### 3.4 Never-negative backstop

A deferred trigger on `journal_lines` refuses any commit that leaves an `investment` or `collection` account below zero:
- as of the latest business date; and
- as of any later business date (the `min_balance_from` logic, run only for the accounts touched in that transaction).

It's the database version of today's `reverse_deposit` / `approve_withdrawal` checks.

## 4. Posting rules

Notation: **Dr / Cr** role (subledger). The GL account comes from the role. "MCA" = the borrower's member collection account (02 ADR-02-2).

### 4.1 Investments (today's business)

| Event | Business date | Lines | Notes |
|---|---|---|---|
| `INV_DEPOSIT_POSTED` | deposit `value_date` | Dr Bank (by receiving `company_bank_account`, default by method) / Cr Investor funds 2100 (investment account) | Replaces today's "posted deposit". |
| `INV_DEPOSIT_REVERSED` | **original value date** (open period required; today's rule) | Mirror of the deposit entry, `reverses_entry_id` set | Plus the reversal notice email (exists). |
| `INV_WITHDRAWAL_APPROVED` | withdrawal `value_date` | Dr Investor funds 2100 (account) / Cr Bank (paying account) | Pending withdrawals post **nothing**. They are an `account_holds` row (available balance) until approved. On rejection the hold is released. |
| `INV_INTEREST_APPROVED` | `period_end` | Per payout: Dr Interest expense 5100 / Cr Interest payable 2110 (account) for **gross**. If tax > 0: Dr Interest payable 2110 (account) / Cr WHT payable 2120 | One entry per period, N lines. Interest **never touches 2100**, preserving "interest is paid out, never added to the balance". |
| `INV_INTEREST_PAID` | date marked paid (Nairobi) | Dr Interest payable 2110 (account) / Cr Bank | Per payout. |
| `INV_INTEREST_ACCRUAL_ESTIMATE` *(optional, ADR-03-6 C)* | month end | Dr 5100 / Cr 2800 accruals; auto-reversed on approval | Finance option. |
| `INV_PLACEMENT_*` *(only if term placements, Q-M1)* | daily / maturity | FSD p.65 flows (daily accrual, monthly WHT, break, maturity, rollover) | Not built until confirmed. |

### 4.2 Lending: origination and disbursement

| Event | Lines | Notes |
|---|---|---|
| `LOAN_DISBURSED` | Dr Loan principal 1200 (loan acct) / Cr MCA 2200 (party MCA) for the **gross** principal | FSD "amount financed to customer". Tranches post one entry each. |
| `LOAN_FEE_DEDUCTED` (per fee with `treatment=deduct_at_disbursement`) | Dr MCA 2200 / Cr Fee income 4300 (`income`), or Cr Pass-through payable 2300 (`pass_through`: tracking, risk fund, insurance premium) | Resolves C-5. |
| `LOAN_FEE_CAPITALISED` (`treatment=capitalise`) | Dr Loan principal 1200 (loan) / Cr Fee income or 2300 | The FSD's "fees affect principal". ⚠ IFRS 9 may require integral fees to be deferred over the effective interest rate (EIR) instead (Q-F10). |
| `LOAN_NET_PAYOUT` | Dr MCA 2200 / Cr Bank | "Net amount payable to client". |
| `IPF_PREMIUM_PAID_TO_INSURER` | Dr MCA 2200 / Cr Assurance premium payable 2300 (insurer) | Insurance premium financing pays the insurer, not the client. |
| `OD_LIMIT_CHARGES` / `OD_DRAWDOWN` | Charges: Dr Overdraft 1200 (OD acct) / Cr MCA, then fee lines as above. Drawdown: Dr Overdraft 1200 / Cr MCA; Dr MCA / Cr Bank | FSD overdraft section. |

### 4.3 Lending: accruals, classification, penalties, fees

| Event | Lines | Notes |
|---|---|---|
| `LOAN_INTEREST_ACCRUED` (daily, accruing loans) | Dr Interest receivable 1210 (loan) / Cr Interest income 4100 | One EOD entry per product per branch, with per-loan subledger lines on 1210. Day count per product (C-4). Bullet products accrue daily too (C-10). |
| `LOAN_INTEREST_ACCRUED_SUSPENDED` (daily, NPL) | Dr Interest receivable 1210 (loan) / Cr Interest in suspense 1211 | FSD "91st day". |
| `LOAN_MOVED_TO_SUSPENSE` (on classification to non-accrual) | Dr Interest income 4100 / Cr Interest in suspense 1211 for **accrued-but-unpaid** interest recognised while performing | Prudential practice. Configurable per classification set (Q-F5). |
| `LOAN_RETURNED_TO_ACCRUAL` | Reverse of the above for the amount still unpaid, if policy allows | Optional (Q-F5). |
| `LOAN_PENALTY_CHARGED` (DD + grace days) | Performing: Dr Penalty receivable 1220 / Cr Penalty income 4200. NPL: Cr Penalty in suspense 1221 instead | Basis and rate per product (C-2). Disabled for check-off by default (C-8). |
| `LOAN_RECURRING_FEE` (e.g. monthly tracking) | Dr Fees receivable 1230 (loan) / Cr Fee income 4300, or Cr 2300 for pass-through | Stops at closure. |
| `LOAN_CHARGE_ADHOC` (storage, repossession, advertisement) | Dr Fees receivable 1230 (loan) / Cr 4300 or 2300 | Approval per `loan_charges`. |
| `LOAN_INTEREST_STOPPED` (litigation, special conditions) | No lines. Sets `accrual_status=stopped` via change request | The accrual job skips the loan. |

### 4.4 Lending: receipts and repayment allocation

| Event | Lines | Notes |
|---|---|---|
| `RECEIPT_MATCHED` (M-Pesa C2B, bank, cheque, cash, check-off remittance) | Dr Bank / M-Pesa float / cheques in clearing / Cr MCA 2200 (party) | Matching uses the bill reference = account number, then phone, then manual. |
| `RECEIPT_UNMATCHED` | Dr Bank / Cr Unallocated receipts 2210 | |
| `RECEIPT_SUSPENSE_RESOLVED` | Dr 2210 / Cr MCA 2200 (party) | |
| `REPAYMENT_ALLOCATED` (sweep MCA → loan per waterfall) | Dr MCA 2200 / Cr Penalty receivable 1220, Interest receivable 1210, Fees receivable 1230, Loan principal 1200 (amounts per waterfall) | Default waterfall: penalty → interest → fees → principal (C-6). Overpayment stays on the MCA. |
| `SUSPENSE_RECOGNISED_ON_PAYMENT` (same transaction, NPL loans) | Dr Interest in suspense 1211 / Cr Interest income 4100; Dr Penalty in suspense 1221 / Cr Penalty income 4200, for the amounts just collected | FSD "Dr Interest Suspense GL / Cr Interest Income GL". |
| `COLLATERAL_DISPOSAL_PROCEEDS` | Dr Bank / Cr MCA, then `REPAYMENT_ALLOCATED` with the **disposal waterfall** (principal → interest → penalty) | C-6. |
| `REPAYMENT_REVERSED` (bounced cheque, reversed M-Pesa) | Mirror of the receipt and allocation entries | The allocation rows are reversed by negative rows linked to the reversal entry. |
| Inter-branch split (any event whose lines span two branches) | The engine adds Dr Inter-branch due from 1300 (branch A↔B) / Cr Inter-branch due to 2600 so each branch balances on its own | E.g. a customer of branch A pays at branch B. Each branch's trial balance balances independently. |

### 4.5 Lending: restructure, write-off, provisioning, closure

| Event | Lines | Notes |
|---|---|---|
| `LOAN_RESTRUCTURED` | No principal movement unless arrears are capitalised: Dr Loan principal 1200 / Cr Interest receivable 1210 (and fees), for capitalised arrears. Restructure fee: Dr Fees receivable / Cr Fee income | New schedule version. Suspended interest that gets capitalised stays suspended (Q-F5). |
| `PROVISION_RUN` (EOM) | Increase: Dr Impairment expense 5200 / Cr Allowance 1290. Release: the reverse. Per loan (subledger memo on `provision_lines`) | Method: Q-F3. |
| `LOAN_WRITTEN_OFF` | Dr Allowance 1290 (up to the provision held) + Dr Loans written off 5210 (excess) / Cr Loan principal 1200 (loan). Dr Interest in suspense 1211 / Cr Interest receivable 1210. Dr Penalty in suspense 1221 / Cr Penalty receivable 1220. Fees per policy | FSD "nil off provisions and suspense". Maker-checker plus an approval policy by amount. |
| `RECOVERY_AFTER_WRITE_OFF` | Dr Bank (or MCA) / Cr Recoveries 4500 | The loan stays `written_off`. Tracked against the write-off. |
| `LOAN_CLOSED` | No lines needed if the balance is zero. Early-settlement interest charges post as `LOAN_CHARGE_ADHOC` or an interest event first | Closure checklist (FSD p.16) is a workflow, not postings. |
| `COMMISSION_ACCRUED` / `COMMISSION_PAID` | Dr Commission expense 5300 / Cr Commissions payable 2700, Cr WHT 2710. Then Dr 2700 / Cr Bank | Agent/staff commissions. |

### 4.6 Trade finance

Proposed reading of FSD p.54–55 (C-12, finance to confirm under Q-F8):

| Event | Lines |
|---|---|
| `TF_CUSTOMER_FUNDS_RECEIVED` | Dr Bank / Cr MCA 2200 |
| `TF_MARGIN_TAKEN` | Dr MCA 2200 / Cr TF cash margin 2500 (`tf_margin` acct). If the partner bank holds it: Dr Cash margin held at bank (asset 1150) / Cr Bank |
| `TF_BANK_CHARGES` | Dr MCA 2200 / Cr Bank |
| `TF_CRB_CHARGE` / `TF_CR12_CHARGE` | Dr MCA 2200 / Cr Fee income 4300 |
| `TF_COMMISSION` | Dr MCA 2200 / Cr Guarantee commission income 4400 |
| `TF_GUARANTEE_ISSUED` / `TF_GUARANTEE_EXPIRED` | Memo: Dr Contingent – guarantees issued 9100 / Cr Contingent – customer obligation 9200 (reversed on expiry) |
| `TF_MARGIN_REFUND` | Bank refunds the margin: Dr Bank / Cr 1150. Client refund: Dr 2500 / Cr MCA, then Dr MCA / Cr Bank |

### 4.7 Finance and treasury

| Event | Lines |
|---|---|
| `MANUAL_JOURNAL` | As drafted. Maker-checker. Restricted accounts blocked. |
| `DEPRECIATION_RUN` (EOM) | Dr Depreciation 5400 / Cr Accumulated depreciation 1510 (per category and branch) |
| `PREPAYMENT_AMORTISED` (EOM) | Dr Expense / Cr Prepayments 1400 |
| `BORROWING_RECEIVED` / `BORROWING_INTEREST_ACCRUED` / `BORROWING_INTEREST_PAID` | Dr Bank / Cr Borrowings 2400. Dr Interest expense 5110 / Cr Interest payable 2410. Dr 2410 / Cr Bank, Cr WHT 2420 |
| `TBILL_PURCHASED` / `TBILL_INTEREST_ACCRUED` / `TBILL_MATURED` | Dr Securities 1600 / Cr Bank. Dr Accrued interest (1600 child) / Cr Treasury income 4600. Dr Bank / Cr Securities, accrued interest |
| `YEAR_END_CLOSE` | Dr each income account / Cr each expense account → net to Retained earnings 3xxx |
| `FX_REVALUATION` *(disabled)* | Unrealised gain/loss on FCY balances (ADR-02-4) |

## 5. Period close and EOD integration

| Run | GL responsibilities |
|---|---|
| **EOD** (business date D) | Penalty charges; loan accruals (interest or suspense); classification transitions and suspense transfers; MCA sweeps; recurring fees due; snapshot balances; verify the snapshot equals the line aggregate for touched accounts; trial balance check (Σdr = Σcr per branch). |
| **EOM** | EOD for the last day; provisions; depreciation; prepayments; borrowing and T-bill accruals; **investor interest approved for the month (blocking)**; bank reconciliations complete (warning); close `gl_periods` to `soft_closed`, then `closed` after finance sign-off. |
| **EOY** | EOM; year-end close journal; open the new year's periods. |

Runs are idempotent and resumable (ADR-04-3). A run refuses to close while risk "blocking cases" are open (FSD case management).

---

## 6. Reports the GL enables (phase 11)

- **Statements:** trial balance (company, branch, date range), balance sheet, P&L, GL detail with drill-down (TB → entry → source record).
- **Subledger reconciliations:** Σ control account = Σ subledger balances, for every control account. This runs as an EOD check too.
- **Account statements:** investor (exists, re-sourced), loan, MCA.
- **Exports:** journals and TB to CSV/Excel for auditors or an external package (Q-F9).

---

## 7. Moving the existing investor ledger onto the GL

### 7.1 Principles

- **The investor books are live.** The move must be invisible to investors, provable to the cent, and reversible until switch-over.
- **Nothing in today's tables is deleted or edited.** Deposits, withdrawals, interest periods and payouts stay as the business records. The GL is *added* as the accounting record of the same facts.
- **One module decides balances throughout.** `ledger.py` switches its source behind a setting, not its callers.

### 7.2 Mapping of historical records

| Source rows | Journals created | Business date | Notes |
|---|---|---|---|
| Every deposit (`posted` **and** `reversed`) | `INV_DEPOSIT_POSTED` | `value_date` | `source=('deposit', id)` |
| Every `reversed` deposit | `INV_DEPOSIT_REVERSED` | **the deposit's `value_date`** | See §7.3. |
| Every `approved` withdrawal | `INV_WITHDRAWAL_APPROVED` | `value_date` | Pending: create an `account_holds` row instead. Rejected: nothing. |
| Every `approved`/`paid` interest period | `INV_INTEREST_APPROVED` | `period_end` | One line pair per payout. Gross / tax / net as stored. |
| Every `paid` payout | `INV_INTEREST_PAID` | `paid_at` in Nairobi time | |
| `draft` interest periods | Nothing | — | Recalculated or approved after cutover through the normal path. |

**Bank accounts.** History doesn't record which company bank account received each deposit. Default mapping by method:

| Method | GL account |
|---|---|
| `bank_transfer` | 1100 "main bank account" |
| `mpesa` | 1110 |
| `cheque` | 1120 → 1100 (cleared) |
| `cash` | 1130 |

Finance must confirm this, or supply a mapping table (Q-F4).

**Opening periods.**
- GL periods are created from the month of the first deposit.
- Months covered by approved or paid interest periods are created as `closed` *after* their journals are inserted. The backfill runs as the owner role with the period trigger allowing a flagged `backfill` session only. That's a single migration-time switch, logged.

### 7.3 Why reversals are dated at the original value date

Today a reversed deposit is excluded from **every** balance calculation, including dates before it was reversed:
- `balance_as_of` filters `status = 'posted'`;
- `compute_payouts` uses `balance_events`, which uses only posted deposits.

That's safe only because a reversal is refused when the deposit's value date is in a locked (approved) interest month (`assert_not_locked`). If the GL reversal were dated on the day it happened, GL balances between the value date and the reversal date would include the deposit, and the reconciliation in §7.4 would legitimately fail.

Dating the reversal at the original value date reproduces today's semantics exactly. The period lock that prevents it in closed months is the same lock. After cutover the rule continues:
- reversal at the original value date if that period is open;
- otherwise refused, as today.

A finance-approved "late correction" event dated today (Q-F5) may later be offered for closed periods.

### 7.4 Reconciliation (must match to the cent)

A command, `flask --app main gl reconcile-investors [--as-of DATE]`, compares the GL with the legacy calculation. A test runs the same command against seeded data. **Every check must report zero differences.** Any difference fails the migration and is listed by investor and date.

| # | Check | Legacy side | GL side |
|---|---|---|---|
| R1 | Balance per investor on **every date a balance changed**, and today | `balance_as_of(investor, d)` from deposits/withdrawals | Σ(credit − debit) on 2100 lines for the investment account with `business_date ≤ d` |
| R2 | Minimum balance from each date (overdraw protection) | `min_balance_from` legacy | `min_balance_from` GL |
| R3 | Total investor funds | Σ legacy balances | 2100 control balance, **and** Σ subledger (subledger reconciliation) |
| R4 | Interest per investor per approved period | `interest_payouts.gross_interest / tax_amount / net_interest` | Lines of `INV_INTEREST_APPROVED` for that period and account |
| R5 | **Interest recomputed from GL balances** | Stored payouts | `compute_payouts(period)` with `balance_events()` sourced from the GL. Proves interest would be identical going forward. |
| R6 | Interest outstanding per investor | Σ unpaid net payouts (`investor_totals.interest_payable`) | 2110 subledger balance |
| R7 | Interest paid per investor | `investor_totals.interest_paid` | Σ `INV_INTEREST_PAID` lines |
| R8 | Counts | Deposits, reversed deposits, approved withdrawals, approved periods, paid payouts | Journals per `source_type`/`event_code` |
| R9 | Trial balance | — | Σdebit = Σcredit overall and per branch. Every control account equals Σ its subledger. |
| R10 | Statement golden files | Existing account and interest statement PDFs' *figures* for every investor | Same figures generated from GL-sourced `ledger_entries()` |

### 7.5 Cutover sequence (phase 4)

1. **Ship the GL** (tables, triggers, posting engine, chart seed) with `LEDGER_SOURCE=legacy`. Nothing reads the GL yet.
2. **Backfill** in a maintenance window: run as a dry-run on a copy of production, fix mappings until R1–R10 are clean, then commit on production. The command is idempotent (unique source keys), so a re-run adds nothing.
3. **Dual-write.** New deposits, reversals, withdrawals, interest approvals and payout payments post GL journals *in the same transaction* as today's rows (`ledger.post` called from the existing services). `LEDGER_SOURCE=shadow`: reads still come from legacy, and a nightly job runs R1–R9 and alerts on any difference.
4. **One full month-end in shadow** (interest calculated, approved and paid) with zero differences.
5. **Switch reads.** `LEDGER_SOURCE=gl`: `ledger.py` computes from GL lines. Legacy computations remain as `ledger_legacy.py` for the reconciliation job only.
6. **After two clean month-ends,** remove `ledger_legacy.py`. Deposits and withdrawals stay as business records referencing their journal entries.

**Rollback.** Before step 5 it's free: the GL is only additive. After step 5, flip the setting back to `shadow`. Legacy tables were never stopped being written.

### 7.6 Tests added with phase 4

- **Database invariants:** unbalanced entry rejected at commit; one-line entry rejected; UPDATE/DELETE on journal tables rejected; posting into a closed period rejected; control-account line without a subledger rejected; investment account driven negative rejected.
- **Posting engine:** every event in §4.1 produces the documented lines; idempotency (same source twice → one entry); reversal mirrors the original.
- **Reconciliation:** R1–R10 on the full existing test fixtures plus the demo seed, including reversed deposits, mid-month rate changes, approved and unpaid periods, and paid periods.
- **Existing tests:** all 80 tests pass in `legacy`, `shadow` and `gl` modes (parametrised fixture).
