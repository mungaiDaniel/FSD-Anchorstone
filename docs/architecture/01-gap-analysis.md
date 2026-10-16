# 01 — Gap analysis: FSD vs the current system

**Scope.** This compares every section and requirement group in `docs/fsd.md` (the template FSD from another lender) with the code on `main` as of 2026-10-16.

**The FSD is a template.** Its product names, rates, fees, vendor, branch lists and contact placeholders are examples. The table records *capabilities*, not those values.

**Status key**

| Status | Meaning |
|---|---|
| **Exists** | The current system meets the requirement as written (or close enough that only configuration differs). |
| **Modify** | Something exists but must be extended or reshaped. |
| **New** | Nothing exists yet. |
| **Out of scope** | Excluded by the brief (e.g. the IT wishlist's HR/procurement/registry modules), or a requirement on the vendor rather than the system. |

**Module names** in "where it lives" are the proposed `backend/app/<Module>/` folders from `02-domain-model.md` and `06-phase-plan.md`. "Phase N" refers to the refined plan in `06-phase-plan.md`.

## What exists today (baseline)

The current system is the **investments (funding) side only**.

| Area | Current implementation |
|---|---|
| Investors | `app/Investors`: one running account per investor, `ACL-000001` codes, one investor per email, basic KYC fields (ID number, KRA PIN, payout details), active/closed. |
| Deposits and withdrawals | `app/Transactions`. Deposits post immediately and are reversed (never edited). Withdrawals are maker-checker. The balance lives in `ledger.py` (single source). |
| Interest | `app/Interest`: one flat annual rate with history. Daily closing balance × rate ÷ 365, calculated monthly. Draft → approve (a different admin) → paid. Approved months are locked. Withholding tax is modelled at 0%. |
| Email | `app/Emails`: outbox with retries, deposit/withdrawal confirmations, reversal notices, interest statements and account statements (PDFs stored at creation), AUM report. |
| Reports | `app/Reports`: 7 Excel reports and a scheduled AUM summary. |
| Security | Admin-created accounts, forced password change, roles `user` / `admin` / `super_admin` read from the DB on every request, lockout and per-IP limit, audit log written in the same transaction. |
| Operations | APScheduler in the web process (email queue, AUM report, optional `pg_dump` → OneDrive backup). |

There is **no** general ledger, branch, party/KYC model, document store, lending, SMS, M-Pesa integration, or permission system beyond the 3 roles.

---

## 1. Introduction, objectives, scope, assumptions (FSD p.6–7)

| FSD section | Requirement summary | Status | Where it lives / will live | Notes |
|---|---|---|---|---|
| Introduction | Core system for a non-bank lender with branches | Modify | Whole system | Anchorstone runs **both** funding and lending on one system. The FSD describes a lender whose funding side is private placements. |
| Key business objectives | Customer management, TAT, efficiency, reporting, document management, real-time customer updates | Modify | Phases 2–12 | "Real-time update to customers" implies a customer channel. There is no investor or borrower portal today, and the current decision is "no investor portal". See Q-M3. |
| Project scope (in-scope list) | Onboarding, loans, finance, placements/borrowings, trade finance, documents, risk & audit, IT, integrations | Modify | Phases 2–13 | All in scope except the IT wishlist modules (below). |
| Company/branches table | 7 branches (0–6) | New | `Branches` (phase 2) | ⚠ **Contradiction:** see C-1. |
| Key assumptions | Migration from old core, API integration with 3rd parties, workflows restored | Modify | Phase 13; phase 10 | "Eazzy Books" is the template's vendor; ignore. |

## 2. Customer journey and onboarding: KYC & facility documentation (FSD p.7–10)

| FSD section | Requirement summary | Status | Where it lives / will live | Notes |
|---|---|---|---|---|
| Customer journey / logical loop | Proof of identity, proof of income, collateral, insurance → credit analysis → limit | New | `Parties`, `Documents`, `DocAI`, `Screening`, `Origination` (phases 2–5) | The **new AI pre-selection step** sits between document capture and credit analysis. |
| Onboarding via facility application | Onboarding data captured and stored after approval | New | `Origination` (phase 5), `Parties` (phase 2) | — |
| Maker-checker on static data | Any capture or amendment of static data needs maker-checker | Modify | `Approvals` framework (phase 2) | Today only withdrawals and interest periods are maker-checker. Investor edits are **not**. ⚠ This changes current behaviour (staff edit investor details directly). See Q-M5. |
| Individual KYC fields | Classification, salutation, name, gender, ID/alien no., PIN, DOB, marital status, phones, email, sector, nature of business, addresses, bank details, PEP, RM code/staff no., agent, branch, employer | Modify | `Parties` → `party_persons`, `party_contacts`, `party_bank_accounts` (phase 2) | Investors hold name, email, phone, ID number, KRA PIN and payout details. The rest is new. "Fields in bold are mandatory", but bold didn't survive the PDF: mandatory fields are **ambiguous** (Q-C1). |
| Company KYC fields | Classification, name, reg no., PIN, reg date, phones, email, sector, business, address, directors (name, ID, phone, DOB) and signatories, bank details, risk factor, PEP, RM, branch | New | `Parties` → `party_organisations`, `party_relationships` (director/signatory) | Directors become parties linked by relationship (see 02). |
| Next of kin | Name, relationship, phone, email, address | New | `party_relationships` (role `next_of_kin`) | — |
| Image capture | ID front/back, photo, signature, KRA PIN, CR12, certificate of incorporation, other | New | `Documents` (phase 2), `DocAI` (phase 3) | — |
| Guarantor details | Name, ID, PIN, relationship, phone, address, email | New | `party_relationships` (role `guarantor`), `loan_guarantors` (phase 5) | — |

## 3. Credit operations: member account creation (FSD p.10–12)

| FSD section | Requirement summary | Status | Where it lives / will live | Notes |
|---|---|---|---|---|
| Member account creation | Capture customer + next-of-kin details | Modify | `Parties` | — |
| Update static data via maker-checker | Amendments approved by a second person | New | `Approvals` | See above. |
| Audit trail of static data changes | Full history | Exists → Modify | `audit_logs` (exists) + change-request history | Exists for investors via `UPDATE_INVESTOR` old/new values. It must extend to every party field. |
| Blacklist validation | Check new and existing customers against a blacklist | New | `Risk` → `watchlist_entries` (phase 11, basic version in phase 2) | Screening at onboarding must exist before lending goes live, so a minimal blacklist is in phase 2. |
| Single customer view | All relationships (holder, signatory, agent, shareholder, guarantor) | New | Party 360 view (phase 2, enriched each phase) | This is the main argument for the party model (ADR-02-1). |
| Duplicate detection | Flag existing ID/phone/KRA PIN at onboarding, any branch | New | `Parties` (phase 2) | Unique indexes on normalised ID/KRA PIN/company reg no. Phone is a *warning*, not unique (shared phones are common). |
| Merge duplicate customers | Merge while maintaining history (sentence truncated in the FSD) | New | `Parties` merge (phase 2, maker-checker) | ⚠ **Ambiguous:** the FSD sentence is cut off ("while maintaining"). Assumed: keep history and mark the merged party as `merged_into`. |
| Prevent duplicates by unique ID | An ID can't be registered twice | New | `Parties` | Existing investors have optional, non-unique `id_number`. The backfill must detect clashes first (see 02 §6). |
| Images/signatures at account creation | Capture at creation | New | `Documents` | — |
| Reports of captured details | Report on customer creation | New | `Reports` (phase 11) | — |
| Link related parties | Related-party links | New | `party_relationships` | — |
| PEP prompts | Extra information when PEP | New | `Parties` + `Risk` (phase 2 flag, phase 11 EDD) | — |
| Customer types A–I | Individual (local/foreign), SME, corporate, cooperative, NGO, investment group, public institution | New | `party_type` + `customer_category` reference data | Lettering skips G and H. Treated as a reference list, not hard-coded. |
| Branch transfer | Move an account between branches | New | `Branches` + inter-branch journal (phases 2 and 4) | — |
| Custom account numbers | Numbering consistent across the company | Modify | Numbering service (phase 2) | ⚠ **Conflicts with existing codes:** see C-9. |
| General account information | Name, number, type, internal name, customer ID, authorised users | New | `accounts` (02) | — |
| Image/signature/mandate verification | Signatures, photos, capture date and user, amendments kept, mandate display ("any one to sign"), agent info, group accounts | New | `Documents` + `party_mandates` (phase 2) | Mandates matter for **company investors and borrowers**. Today Anchorstone has individual investors only. |

## 4. Loan maintenance and disbursement (FSD p.12–14)

| FSD section | Requirement summary | Status | Where it lives / will live | Notes |
|---|---|---|---|---|
| Loan capture fields | Customer, address, ID/TIN, shareholding %, operative account link, county, rural/urban, fixed/variable interest, repayment dates, schedule, business category, sector, facility type, security incl. valuation dates | New | `Origination`, `Loans` (phase 5) | — |
| Collateral insurance details | Insurer, agency, dates, cover type, document uploads; per-customer/per-loan reports; expired-insurance dashboard | New | `Collateral`, `Insurance` (phase 8) | — |
| Limit, type, currency, tenor, employer, age, gender, income bracket | Loan and borrower attributes | New | `Loans`, `Parties` | Currency field from day one (ADR-02-4). |
| Guarantor details incl. amount guaranteed | Per-loan guarantee | New | `loan_guarantors` | — |
| Agent details and referral tracking | Agent (non-staff) referrer, mandatory fields, several loans per agent | New | `party_roles` = `agent`; `loans.referred_by_party_id` | — |
| Post-dated cheque register | Banking dates, daily pop-up per branch | New | `Repayments` → `pdc_register` (phase 7) | — |
| Agent/staff commission | % of disbursed amount, daily report, tax deducted | New | `Commissions` (phase 5 calculation, phase 9 payment journals) | ⚠ The withholding rate on commissions isn't given (Q-F6). |
| Restructure, top-up, overdraft, refinance | Supported activities | New | `Loans` (phases 6–8) | Overdraft is a revolving product type (02). |
| Guarantor static data | Captured | New | `Parties` | — |
| Insurance maintenance and renewal monitoring | Track agreement insurance | New | `Insurance` (phase 8) | — |
| SMS alerts for expiring insurance + daily report | SMS | New | `Notifications` SMS channel (phase 10) | There is no SMS gateway today. The email outbox pattern extends to SMS. |
| Disbursement workflow | Request generated when pre-disbursement conditions are met; staged disbursement | New | `Origination` → `disbursement_requests` (phase 5) | — |
| Printable disbursement receipt with charges | Receipt PDF | New | `Documents` / PDF generator (phase 5) | — |
| Related parties | Identify and link | New | `party_relationships` | — |
| Offer letters and fee schedules from templates | Generated per customer | New | `Origination` (phase 5) | Templates are "as shared", but we don't have them (Q-C5). |

## 5. Interest and penalty (FSD p.14–15)

| FSD section | Requirement summary | Status | Where it lives / will live | Notes |
|---|---|---|---|---|
| Flat vs reducing balance per product | Interest method on the product | New | `Products` (phase 5), `Accrual` (phase 6) | Investor interest exists (simple, daily balance). Loan interest is new. |
| 365-day accrual "considering a leap year" | Day count | Modify | `Products.day_count` | ⚠ **Ambiguous:** see C-4. |
| Allocation priority penalty → interest → principal | Repayment waterfall | New | `Repayments` (phase 7) | Configurable per product (C-6). |
| Interest on NPLs to suspense | Suspense GL | New | `Accrual` + GL (phases 4 and 6) | — |
| Suspend interest after 90 days unpaid; adjust on repayment | NPL rule | New | `Classification` (phase 6) | ⚠ **Contradiction** with IPF: see C-7. |
| Map interest/penalty/charges to GL per loan | GL mapping | New | `Ledger` posting rules (phase 4) | — |
| Recalculate schedules on rate/tenor change (keep end date or extend term) | Two recalculation modes | New | `Schedules` (phase 6) | — |
| Suspend interest/penalty for NPLs to suspense; recognise on payment | Suspense accounting | New | `Accrual` + GL | — |
| Automatic reclassification after payments | Normal/Watch/Substandard/Doubtful/Loss | New | `Classification` (phase 6) | The day buckets for each class aren't given (Q-C3). |
| Daily accrual of normal and penal interest | Daily postings | New | `Accrual` EOD job (phase 6, worker from phase 2) | Needs the job queue (ADR-04-3). |
| Daily accrual of suspended interest | Suspense accruals | New | `Accrual` | — |
| Interest by days between instalments | Daily accrual basis | New | `Accrual` | — |
| In duplum rule check | Flag breaches, report | New | `Classification` / `Risk` (phase 6) | ⚠ This is a Banking Act rule. Whether it binds a non-bank lender is a compliance question (Q-CO4). Default: apply it as a control anyway. |
| Max loans for related parties (3) | Booking block | New | `Origination` rule (phase 5) | Configurable limit, not hard-coded 3. |
| Alerts to concerned parties by email | Notifications | Modify | Outbox (exists) → `Notifications` | — |
| SMS/email reminders (instalment, insurance expiry) | Customer notifications | New | `Notifications` (phase 10) | — |
| Custom interest rate per account under maker-checker | Rate override | New | `Loans` + `Approvals` | — |

## 6. Fees and charges (FSD p.15)

| FSD section | Requirement summary | Status | Where it lives / will live | Notes |
|---|---|---|---|---|
| Charge types (LAF, risk fund, bank charges, CRB, legal, membership, tracking (monthly), valuation, insurance premium, search) | Fee catalogue | New | `Products` → `fee_definitions` (phase 5) | Defined per product by Anchorstone. The FSD amounts are examples. |
| Monthly fee deduction | Recurring fees | New | `Accrual` / EOM (phase 6) | — |
| Show fees debited on the loan | Statement lines | New | `Loans` statement | — |
| Fees affect principal and are cleared as principal | Capitalised fees | New | `Products.fee_treatment` | ⚠ **Contradiction:** see C-5. |
| Ad-hoc charges (storage of repossessed collateral, etc.) | Other charges into the outstanding balance | New | `Loans` → `loan_charges` (phase 8) | — |

## 7. Loan repayments (FSD p.15–16)

| FSD section | Requirement summary | Status | Where it lives / will live | Notes |
|---|---|---|---|---|
| Frequencies daily → yearly, bullet | Schedule frequencies | New | `Products`, `Schedules` (phases 5–6) | — |
| Expected repayments report per month | Report | New | `Reports` (phase 11) | — |
| Mixed schedules (P+I, interest-only, bullet) | Schedule types | New | `Schedules` | — |
| Early settlement and surcharge | Settlement quote | New | `Repayments` (phase 7) | — |
| Standard instalment from term, rate and balance | Amortisation | New | `Schedules` | — |
| Lump-sum principal repayments | Prepayment | New | `Repayments` | Whether the term shortens or the instalment reduces is a product option (Q-C7). |
| Posting to a chosen loan when the customer has several | Allocation target | New | `Repayments` | — |
| Change repayment dates via maker-checker | Date change | New | `Loans` + `Approvals` | — |
| Rescheduling (dates and amounts) | Reschedule | New | `Schedules` (phase 8 with restructures) | — |
| Settlement statement incl. fees | Quote | New | `Repayments` | — |
| Auto-deduct the due instalment from the member collection account | Sweep | New | `Repayments` EOD sweep (phase 7) | Depends on the "member collection account" concept (02 ADR-02-3). |
| Controlled loan closure (closing interest, closing entries, stop periodic fees, CRB notice, clearance letter, release securities, cancel insurance) | Closure workflow | New | `Loans` closure (phase 8) | — |
| Reversal and closure with suspended interest | Reversal | New | `Loans`, GL reversal | — |
| Allocation order on repayment / on collateral disposal | Waterfalls | New | `Repayments` | ⚠ **Two different orders:** see C-6 (consistent, but both must be configurable). |
| Settlement statements charging future interest | Quote option | New | `Repayments` | — |
| Stop or suspend interest for performing accounts, with approval | Interest stop | New | `Accrual` + `Approvals` | — |
| Display closing balance with all components | Loan statement | New | `Loans` | — |

## 8. Check-off, collateral, restructuring, provisioning, recoveries, litigation, insurance, write-off (FSD p.16–19)

| FSD section | Requirement summary | Status | Where it lives / will live | Notes |
|---|---|---|---|---|
| Check-off: gross disbursement, employer list, no penalty, instalment breakdown, ledger allocation, bulk payments + auto-reconcile | Employer-deducted loans | New | `Products` (flag `checkoff`), `Employers`, `Repayments` bulk import (phase 7) | ⚠ "No penalty" contradicts "penalty applies to all products" (C-8). |
| Collateral register, several securities per loan, shared collateral | Collateral | New | `Collateral` (phase 8) | The many-to-many link `loan_collateral` is planned from phase 5 so origination can attach security. |
| Guarantor vs borrower security; LTV; unsecured flag on expiry; replacement; partial release; revaluation diary; document preparation tracking | Collateral lifecycle | New | `Collateral` | — |
| Security types (vehicles, land, debentures, set-off, guarantees, T-bills/bonds, shares, other) and their fields (OMV, FSV, insurance value) | Typed collateral | New | `collateral_items` + type-specific JSON attributes | — |
| Restructuring max 3; alert; distinguish from amendments; auto restructure fee | Restructure | New | `Loans` → `loan_restructures` (phase 8) | Configurable maximum. |
| Provisioning classes; suspend interest for NPLs; specific provisions report | Provisioning | New | `Provisioning` (phase 6 classification, phase 8 provisions) | ⚠ Provision rates and IFRS 9 approach not given (Q-F3). |
| Scheduled vs actual tracking, collections diary, correspondence, special arrangements, overdue fees, credit-life maturity, penalty DD+7, CRB notifications, arrears history, manual stop of accrual > 90 days, demand/proclamation/sale notices, recovery reports | Recoveries | New | `Recoveries` (phase 8), CRB (phase 10) | — |
| Litigation flag; stop accrual with approval | Litigation | New | `Loans` flags + `Approvals` | — |
| Insurance details, renewals, premium recovery, expiry alerts, claims tracking | Insurance | New | `Insurance` (phase 8) | — |
| Write-off entries, nil-off provisions and suspense, written-off flag, diary, lien on member accounts, recoveries post write-off, no overdrawing / overpaying | Write-off | New | `Recoveries` + GL (phase 8) | "Lien on member operative account" needs member collection accounts (ADR-02-3). |

## 9. Reporting (credit) and special conditions (FSD p.19–21)

| FSD section | Requirement summary | Status | Where it lives / will live | Notes |
|---|---|---|---|---|
| Scheduled real-time reports saved | Report scheduling | Modify | `Reports` (exists: Excel + scheduled AUM) → generic schedule (phase 11) | — |
| Budget vs actual (MTD/YTD, PAR) | Budgeting | New | `Reports` + `budgets` (phase 11) | Budget capture isn't specified elsewhere (Q-F7). |
| Loan application, disbursement, portfolio classification, overdue, outstanding balance, stopped-interest, due-within-period, rescheduled, NPL reports | Credit reports | New | `Reports` (phase 11) | — |
| Letter-quality overdraft notices | Correspondence | New | `Documents` templates (phase 8) | — |
| Credit exposure by branch/region/county/town/…/income | Exposure analytics | New | `Reports` | Needs these dimensions captured at origination (phase 5). |
| Exceptional behaviour alerts, segmentation, daily repayments (third-party vs client), insurance expiry, exceptions per product, revenue assurance | Reports and alerts | New | `Reports`, `Risk` | — |
| Special conditions: suspend interest but still charge; manual repayment for NPLs; commission flag; stop interest & penalty; waivers; early-settlement interest | Account conditions | New | `Loans` conditions + `Approvals` | "Suspend interest for performing accounts but still charge on client's account" is **ambiguous** (Q-C9). |
| Every posting tagged to a loan or member number | Traceability | New | GL subledger tagging (phase 4) | — |
| Flag staff access to accounts not assigned to them | Access monitoring | New | RBAC data scoping + access log (ADR-04-4) | — |
| Departmental maker-checker; makers and checkers shown on reports | MC | Modify | `Approvals` | Exists for withdrawals/interest. Reports already show recorded/decided by. |
| 360 view | Single view | New | `Parties` | — |
| Birthdays/anniversaries for notifications | CRM | New | `Notifications` (phase 10) | — |
| No overdrawing of loan or member collection account | Hard rule | Modify | `ledger.py` successor (exists for investor balances) | Existing rule: a balance can never go negative. |
| Overdraft maturity dates | OD | New | `Products` (revolving) | — |
| Preferential charges at customer level under maker-checker | Pricing override | New | `Products` → `party_pricing_overrides` | — |
| RM reminders for upcoming obligations | Alerts | New | `Notifications` | — |
| Review dates and review fees | Facility review | New | `Loans` | — |
| Other monthly fees | Fees | New | `Products` | — |

## 10. Loan products and accounting rules (FSD p.22–51)

| FSD section | Requirement summary | Status | Where it lives / will live | Notes |
|---|---|---|---|---|
| Product list (business loans a–d, check-off, Supa Salo, Quick Cash, executive advance, import duty, Mathree, staff, study abroad, Wasanii Boost) | Product catalogue | New | `Products` (phase 5), configured by Anchorstone | ⚠ The list and the accounting sections don't match: see C-3. **Names are template examples.** |
| Per-product fee tables (interest %/month, penalty DD+7, one-off and monthly fees) | Product parameters | New | `products`, `fee_definitions` | ⚠ Penalty 3% here vs 5% in the SMS template (C-2). |
| Business loan (24-month amortising) disbursement, fees, interest, NPL suspense, penalty postings | Posting rules | New | `Ledger` posting rules (phase 4), `Accrual` (phase 6) | All products share one posting skeleton (03 §5). |
| Bullet interest + bullet principal; interest posted on maturity; suspense if unfunded | Bullet products | New | `Schedules` + `Accrual` | ⚠ "Accrues daily" vs "upon maturity posts interest" (C-10). |
| Monthly interest + bullet principal | Interest-only schedule | New | `Schedules` | — |
| Reducing balance (partners) | Reducing method | New | `Products.interest_method` | — |
| Check-off instalment = P+I + insurance + admin fee + processing fee | Composite instalment | New | `Schedules` components | ⚠ The processing fee is monthly here but one-off elsewhere (C-11). |
| Overdraft (limit, drawdown, interest on utilisation) | Revolving facility | New | `Products` type `revolving` (phase 7–8) | — |
| Executive advance, import duty (1 month), payday, staff (reducing, no LAF), asset finance, IPF (first instalment before disbursement) | Variants | New | Configuration of the product engine | IPF's "first instalment before disbursement" becomes a pre-disbursement condition. |

## 11. Trade finance (FSD p.52–55)

| FSD section | Requirement summary | Status | Where it lives / will live | Notes |
|---|---|---|---|---|
| Definitions and products (bid bond, performance bond, APG, bank guarantee, LC) | Guarantee products via partner banks | New | `TradeFinance` (phase 9) | Anchorstone arranges guarantees issued by **banks** and holds cash margins. These are contingent liabilities, not loans. |
| Product features (limits, cash cover %, commission %/quarter, documents) | Parameters | New | `tf_products` | — |
| Validate balance/limit before committing | Limit check | New | `TradeFinance` + `Ledger` | — |
| AML check on beneficiary before processing | AML | New | `Risk` watchlist (phases 2/11) | — |
| Approve/reject AML-flagged items | Workflow | New | `Approvals` | — |
| On approval: entries, voucher, e-mail to e-banking customers | Posting + voucher | New | `Ledger`, `Documents` | "E-banking" customers don't exist here (Q-M3). |
| Return to maker for modification; cancel | Workflow | New | `Approvals` (return-for-edit state) | The framework needs a **returned** state (ADR-04-1). |
| Accounting process table (customer deposit, bank charges, cash margin, CRB, CR12, guarantee income, margin refund) | Posting rules | New | `Ledger` posting rules | ⚠ The "guarantee income" row's DR/CR pairing is broken across the page: see C-12. |

## 12. Finance (FSD p.56–61)

| FSD section | Requirement summary | Status | Where it lives / will live | Notes |
|---|---|---|---|---|
| Accounting functions (COA, categories, branch code, transaction codes, subledgers, integrated real-time) | GL core | New | `Ledger` (phase 4) | ADR-03-1. |
| User-defined periods, drill-down, accruals, BS and P&L per segment | GL features | New | `Ledger`, `Reports` | — |
| Account codes by rule, prior-year TB, segregation by division/department/product/profit centre | Dimensions | New | `gl_accounts` + line dimensions (branch, product, cost centre) | — |
| Batch posting, balanced batches, rollback of unfinished, suspend unbalanced, maker-checker, auto-serial | Manual journals | New | `Ledger` manual journals (phase 9) | Unbalanced *drafts* can be saved. Only balanced journals post (DB-enforced). |
| Cash receipts journal, bank reconciliation, statement import, reports | Cash and bank | New | `Treasury` → bank reconciliation (phase 9) | — |
| Transaction posting with value date, receipts, vouchers, passbook, unique codes | Posting metadata | Modify | `Ledger` | Value dates exist on deposits/withdrawals. "Passbook" printing: Q-IT4. |
| Chart: multi-year, sorting, periods, restructure, multi-currency and multi-entity | COA | New | `Ledger` | Multi-entity is **out of scope** unless confirmed (Q-M6). Multi-currency is modelled but disabled. |
| Reports (GL, TB per branch, IFRS 9 assets/liabilities, custom, MIS, daily P&L and BS per branch/segment, profitability, budget variance, member balances) | Finance reports | New | `Reports` (phase 11) | — |
| Journal entry views, Dr/Cr limit alerts, restrict manual debits on income GLs | JE controls | New | `Ledger` + permissions | — |
| Closings (day, month, year), year-end P&L roll, roll-back window | Period close | New | `Ledger` periods + EOD/EOM/EOY (phase 12) | Existing "approved interest month locks dates" generalises to GL period locks. |
| Prepayments schedule and monthly amortisation | Prepayments | New | `Treasury` → `prepayments` (phase 9) | — |
| Fixed assets register, straight-line monthly depreciation, additions/disposals/revaluations | Fixed assets | New | `FixedAssets` (phase 9) | Category rates are examples. |
| Inter-branch accounts (audit trail, staff/portfolio transfer, cost allocation, RM tagging, finance-only correction, bulk reassign) | Inter-branch | New | `Ledger` due-to/due-from + `Branches` (phases 2/4/9) | Branches go in at phase 2 (ADR-02-3) so no backfill is needed later. |
| Branch list 0–15 | Branches | New | `branches` reference data | ⚠ C-1. |
| Chart of accounts "shared separately" | COA content | New | Seed data | We don't have it (Q-F1). |
| FCY GLs for loans and borrowings | Multi-currency | New | Modelled (ADR-02-4), disabled | — |
| Bonds (FVPL/HTM), T-bills, FX revaluation | Treasury investments | New | `Treasury` (phase 9) | — |

## 13. Funding: private placements and long-term borrowings (FSD p.62–68)

> The FSD's funding section is the **only** part that overlaps the current system. It describes **term placements** (receipts with tenors, maturity, rollover), while Anchorstone today runs **one open-ended running balance per investor** with monthly interest paid out. This is the biggest product question in the brief (C-13, Q-M1).

| FSD section | Requirement summary | Status | Where it lives / will live | Notes |
|---|---|---|---|---|
| Short- and long-term funding | Categories | Modify | `Investments` (existing `Investors`/`Transactions`/`Interest`) | — |
| PP definition and features (negotiable tenor-based rates, booked for a year, quarterly interest, multiple receipts, min/max, WHT 15% unless exempt) | Term placements | Modify | `Investments` → `placement_receipts` (phase 9 or later, if adopted) | Today: one flat rate for everyone, no tenors, monthly payout, WHT 0%. ⚠ C-13. |
| Rate of return by tenor (example table) | Rate card | Modify | `interest_rates` → rate card by tenor | Example values only. |
| Registration: member maintenance, account approval (maker-checker), funds receipt from bank, booking and receipts | Onboarding | Modify | `Parties` + `Approvals` | Investor creation isn't maker-checker today (Q-M5). |
| Management: daily accrual, payout frequencies, close on maturity, due-date notifications, withholding, monthly statement emails | PP lifecycle | Modify | `Investments` | **Exists:** monthly statements, payout tracking, WHT modelled. **New:** daily accrual postings (GL), maturity, frequencies. |
| Lien on placement securing a loan | Cross-sell security | New | `Collateral` (deposit lien type) + `ledger.py` available-balance rule | Requires a "held" amount in the balance logic. |
| Rollover instructions (P+I, P only, liquidate, interest to member account, none) | Maturity instructions | New | `Investments` (if term placements are adopted) | — |
| Reports (customers, active, receipts, matured, categories, WHT per customer, placement statement history) | PP reports | Modify | `Reports` | Investors/interest/AUM reports exist. WHT report new. |
| Categorisation (HNI, corporates, SACCOs, investment groups, fund managers, insurers, churches, financial advisors with sub-accounts) | Investor categories | New | `party` category + `investor_category` + advisor relationship | Advisor sub-accounts map to `party_relationships` (`referred_by`). |
| PP accounting rules (daily accrual, monthly WHT, liquidation/break, maturity, payment vouchers, rollover) | Posting rules | New | `Ledger` (phase 4) | 03 §5.1 maps today's monthly model. Daily accrual is optional. |
| PP glossary (maturity instructions, payment frequencies, booking 30D…365D) | Reference data | New | `Investments` reference data | — |
| PP report templates (placement report/statement, WHT, sector) | Reports | Modify | `Reports` | Statements exist. |
| Long-term borrowings (bank loans, venture funding) and their accounting | Liabilities | New | `Treasury` → `borrowings` (phase 9) | Interest accrual and WHT posting. |

## 14. Risk and audit (FSD p.69–71)

| FSD section | Requirement summary | Status | Where it lives / will live | Notes |
|---|---|---|---|---|
| Credit, operational, market and liquidity risk; customer rating, scoring, loan-loss indicators, liquidity barometer; centralised limits with maker-checker; exposure monitoring | Risk module | New | `Risk` (phase 11) | The AI pre-selection score feeds credit, but is **not** a credit rating (05). |
| AML: profiling, watchlists/blacklists (fraud, defaulters, PEP, tax, terrorism), archive, transaction monitoring vs declaration limits, suspicious activity, alert case management, workflow violations, exception reporting | AML | New | `Risk` → `watchlist_entries`, `aml_alerts`, `cases` (phase 2 minimal, phase 11 full) | The FSD mentions "integrate with the company AML system" in trade finance. Whether one exists: Q-CO6. |
| Case management (outstanding exceptions blocking EOD, owner, ageing, investigation status, incident reports, AML officer hierarchy) | Cases | New | `Risk` → `cases` | "Restrict end-of-day until resolved" ties into the EOD design (ADR-04-3). |
| Audit control logs (activity by day/user/workstation, errors, **users viewing customer data**, utilities, maintenance, immutable logs, alerts on classified accounts) | Audit | Modify | `audit_logs` (exists) | **Exists:** changes, IP, user agent. **New:** *read* access logging of customer data, immutability enforced in the DB (today it's application convention), alerts. |
| Security authorisation by user/group/function area/access type | RBAC | Modify | ADR-04-4 | 3 fixed roles today. |
| No deletion of transactions; originals kept with who and when | Immutability | Exists → Modify | Deposits/withdrawals/interest (exists) → GL triggers (phase 4) | ⚠ Users can be hard-deleted today (`DELETE /users/<id>`). Recommend disable-only (Q-IT2). |
| Audit data-mining from the DB | Read access | New | Read-only reporting role / replica (phase 12) | — |
| Compliance: transaction limits, high-risk marking, sanctions monitoring, sanctions DB (UNSC), updatable rules | Compliance | New | `Risk` (phase 11) | — |

## 15. Information technology (FSD p.72–76)

| FSD section | Requirement summary | Status | Where it lives / will live | Notes |
|---|---|---|---|---|
| IT functions: user admin, role centres, workflows; level I–IV support; process monitoring (interest billing/posting, email/SMS, services); DB admin (backups, restore, SQL, reports); policy enforcement; training; documentation; audit trails | IT operations | Modify | Users (exists), jobs dashboard (phase 12), backups (exists) | Backups exist (OneDrive, off by default). **Restore has never been tested** (Q-IT3). |
| Merits to retain (modules, integrations, docs, role centres, client audit trail, dashboards, exports, process controls, data classification, versioning, automation with manual fallback, EOD/EOM/EOY, policy enforcement, GUI) | Non-functional | Modify | Across phases | Data classification → document sensitivity labels (ADR-04-2). |
| Wishlist: hardware/OS/storage/backup/mirror site, DB (Oracle/MySQL), BI, bandwidth, WAN/VPN | Infrastructure | Out of scope / Modify | — | ⚠ **"Oracle, MySQL Server" contradicts the decision to use PostgreSQL only** (C-15). PostgreSQL stays. Hosting and DR: Q-IT1. |
| Wishlist: software modules (procurement, HR, EDMS, registry, fund), tablet apps, BI tool, batch processing | Other modules | **Out of scope** (procurement, HR, registry, per brief) / Modify (EDMS → `Documents`; batch → job queue) | — | — |
| Databases: centralised processing, test environment, data querying | Environments | Modify | Phase 12 | — |
| Performance: load and stress testing, concurrency, automated EOD/EOM/EOY, flag unbalanced transactions | Performance | New | Phase 12 | — |
| Backup and recovery: crash handling, automatic back-out of incomplete transactions, restart | Resilience | Modify | PostgreSQL transactions (exist) + idempotent jobs (ADR-04-3) | — |
| Security: encryption in transit/at rest, granular rights, maker-checker on all transactions, audit of access, transaction IDs, **password policy (8 chars, no reuse, monthly expiry, no remember-me, idle timeout, single session)**, independent rights allocation, per-user limits, time-based access, print and export control, encrypted passwords, versioning, restricted copy/paste, APIs, suspense for failed API transactions, alternate channels | Security | Modify | `Admin` (exists), ADR-04-4 | Today: min 10 characters with letters+digits (stronger than 8), lockout, JWT 12 h. **New:** reuse history, expiry, idle timeout, single session, time-based access, export control. "Restricted copy/paste" in a web app is cosmetic only (Q-IT5). |
| Workflows and messaging (multi-level approvals by amount/type, notifications, internal and external email/SMS, sent/failed/pending audit) | Workflow | Modify | `Approvals` + outbox (exists) | The outbox already records sent/failed/pending. |
| Automated processes (schedule, monitor, pause, stop; logs; manual fallback) | Jobs | Modify | ADR-04-3 | — |
| Reporting (Excel/CSV/PDF/Word export, scheduling, report designer, standard reports, MIS graphs) | Reporting | Modify | `Reports` (Excel exists) | A drag-and-drop report designer is **out of scope**. Recommend export to a BI tool instead (Q-IT6). |
| Ease of use (validation, pop-ups, manuals, training) | UX | Modify | Ongoing | — |
| Vendor support (24/7, on-prem, issue log, resolution matrix) | Vendor obligations | Out of scope | — | A contract matter, not a system feature. |

## 16. Integrations, migration and reports (FSD p.76–80)

| FSD section | Requirement summary | Status | Where it lives / will live | Notes |
|---|---|---|---|---|
| M-Pesa Paybill C2B | Incoming payments | New | `Payments` → M-Pesa C2B callbacks + suspense (phase 7) | — |
| SMS gateway | Outgoing SMS | New | `Notifications` SMS provider adapter (phase 10) | Provider not chosen (Q-IT7). |
| M-Pesa transaction receipts | Receipts | New | `Payments` | — |
| API testing and sign-off (endpoints, no test data in prod, all platforms, data feeds, access) | Integration testing | New | Phase 10 acceptance criteria | — |
| (Not in FSD) CRB submissions | Credit bureau | New | Phase 10 | The FSD requires CRB notifications in several places but lists no CRB integration (C-14). |
| Static data migration (active customers and balances, KYC, products, tariffs, loan parameters, balances as at cutoff, unchanged GL numbers, **11-digit client numbers** with branch+product code, lien charges) | Migration | New | Phase 13 | ⚠ The source system for Anchorstone's lending book is unknown (Q-IT8). The investor book is already in this system. |
| Migration audit (counts, balances, GL, schedules, product mapping) | Reconciliation | New | Phase 13 | Same reconciliation approach as the GL backfill (03 §7). |
| Credit department reports (loan list, PAR, repayments, collateral) per individual/branch/segment/company | Reports | New | `Reports` (phase 11) | — |
| SMS templates (disbursement, due in 7 days, due today, arrears, penalty 5%, repossession warning, insurance expiry) | SMS content | New | `Notifications` templates (phase 10) | ⚠ C-2. The repossession wording has legal implications (Q-CO7). |
| Investor relations reports (placement register, placement report, savings report, WHT register, alerts on placements falling due) | IR reports | Modify | `Reports` | "Savings report" implies a savings product that's described nowhere (C-16). |
| Private placement email notification template | Statement email | Exists → Modify | `Emails` (interest and account statements exist) | Anchorstone's template is already branded and approved. |
| Finance reports (BS, IS, TB, commission payments) | Finance reports | New | `Reports` (phase 11) | — |
| Report templates (section empty in the FSD) | — | — | — | Nothing to implement. |

## 17. Not in the FSD but required by the brief

| Requirement | Status | Where it lives / will live | Notes |
|---|---|---|---|
| AI extraction from scanned documents (ID, KRA PIN, CR12, incorporation, bank and M-Pesa statements, financials, title deeds, logbooks, valuations) | New | `DocAI` (phase 3) | `05-ai-document-pipeline.md` |
| Rules-based pre-selection (Shortlisted / Needs review / Not qualified) before credit analysis | New | `Screening` (phase 3) | Admin-configured, versioned rules. The AI never decides. |
| Kenya Data Protection Act 2019 controls (consent, minimisation, retention, access logging) | New | `Parties` consent, `Documents` retention, audit read-logging | Applies to the **existing investor data too**, not just AI (Q-CO1). |
| Configurable product engine (no template product names in code) | New | `Products` (phase 5) | — |

---

## Contradictions and ambiguities in the FSD

| # | Where | Problem | Recommended handling |
|---|---|---|---|
| C-1 | p.7 vs p.60 vs p.6 | The intro says **9 branches**. The project scope lists **7** (0–6, including "Mombasa Rd" and Eldoret). Inter-branch lists **16** (0–15, with different names). | Branches are reference data maintained by admins. Anchorstone supplies its own list (Q-M4). |
| C-2 | Product tables vs SMS templates (p.78) | Penalty is **3%/month** in every product table, but the SMS says "continues to attract a penalty of **5%**". | Penalty rate is a product parameter. SMS templates insert the configured rate, never a literal. |
| C-3 | p.22 product list vs p.23–51 accounting | The list has Quick Cash, Study Abroad and Wasanii Boost with no accounting rules. The accounting covers Overdraft, Asset Finance, Payday, IPF and Staff loans, which aren't in the list. | Both lists are template examples. Anchorstone defines its catalogue (Q-C2). |
| C-4 | p.14 | "365 days (considering a leap year)": fixed 365, or 366 in leap years? The current investor side uses **fixed 365 by decision**. | Day count is a product parameter (`ACT/365F` default, `ACT/ACT` available) (Q-F2). |
| C-5 | p.15 vs product accounting | "Fees affect the principal balance and are cleared as principal" (capitalised), but every product's accounting deducts fees from the disbursement ("net amount payable to client"). | Per-fee treatment: `deduct_at_disbursement` / `capitalise` / `bill_separately` (Q-C6). |
| C-6 | p.16 | Repayment order is **penalty → interest → principal**, but collateral-disposal proceeds go **principal → interest → penalty**. | Not a contradiction, but two configurable waterfalls keyed by payment source. |
| C-7 | p.14 vs p.51 | General NPL rule: suspend after **90 days unpaid** (91st day). IPF: "any account falling due and not funded → non-performing" (day 1). | Classification thresholds per product (Q-C3). |
| C-8 | p.16 vs p.18 | Check-off has "no penalty interest", while recoveries says penalty applies 7 days past due "to all products". | `penalty_enabled` per product. Check-off defaults to off. |
| C-9 | p.11 / p.77 vs existing system | The FSD wants customised account numbers and an **11-digit client number** (branch + product + customer). Investors already use **`ACL-000001`**, which appears on statements and emails. | Keep `ACL-…` for investment accounts. New party numbers and loan account numbers follow the new scheme (Q-M2). |
| C-10 | p.25 | Bullet product: "account accrues daily" but "upon maturity posts the interest payable to income". | Accrue daily into receivable/suspense. Maturity triggers classification only (03 §5.3). |
| C-11 | p.31 | Check-off instalment includes a *processing fee* monthly, while LAF is one-off for every other product. | Fee frequency is per fee definition (Q-C6). |
| C-12 | p.55 | Trade finance "income earned from guaranteed product": the DR/CR rows for guarantee income and cash-margin refund are split across a page break and the pairing is unclear. | Re-confirm with finance (Q-F8). Proposed reading in 03 §5.6. |
| C-13 | p.62–66 vs current product | The FSD describes term placements (tenors, maturity, rollover, 15% WHT, rate by tenor). Anchorstone runs one open-ended running balance, one flat rate, monthly payout, WHT 0% pending compliance. | Keep the current model. The term-placement engine is a later, optional extension (Q-M1). |
| C-14 | Throughout vs p.76 | CRB notification is required in recoveries, closure and onboarding, but isn't listed as an integration. | Add a CRB integration to phase 10 (Q-CO5). |
| C-15 | p.73 | "Commercially available database such as Oracle, MySQL Server" vs the decision **PostgreSQL only**. | PostgreSQL (decided). The FSD wording is a suggestion. |
| C-16 | p.79 | Investor relations wants a "Savings Report", but no savings product is defined. | Drop unless Anchorstone has a savings product (Q-M1). |
| C-17 | p.13 vs p.15 | Interest is "fixed and variable" at capture, while the rate section only describes flat and reducing *methods*. | Separate *rate type* (fixed/variable with a base rate) from *method* (flat/reducing) (Q-C4). |
| C-18 | p.73 | Password policy "8 characters minimum, monthly expiry" vs current stronger minimum (10) and no expiry. NIST guidance discourages forced periodic expiry. | Keep 10 characters. Add reuse history. Expiry configurable, default off (Q-IT5). |
| C-19 | p.14 | "Maximum loan accounts allowable are 3" for related parties: per borrower, or per related-party group? | Configurable limit per borrower group (Q-C10). |
