# 08 — Working assumptions and runtime settings

We're building now with our own defaults and will confirm them with Anchorstone later. This document does three things:
1. records the value in use for every open question in `07-open-questions.md`;
2. flags where 07 and the FSD v0.1 working assumptions (WA-01 to WA-14) disagree;
3. designs how these values become **versioned runtime settings changed under maker-checker**, so that when the client answers we change settings, not code.

**Sources**

| Source | What it is |
|---|---|
| **FSD v0.1** | *Anchorstone Capital Ltd — Functional Specification v0.1* (16 Oct 2026, "Project team"), Section 20 working assumptions. The file was read from `Downloads/Anchorstone_FSD_v0.1.pdf`; it isn't in `docs/` yet. |
| **07** | `docs/architecture/07-open-questions.md` (recommended defaults). |
| **Our questionnaire** | `deliverables/Anchorstone-Client-Questionnaire.docx` (question IDs A1–I12). |

**Rule applied.**
- Where the FSD gives a WA value, it is the value in use, even when 07 recommended something else (conflicts in §2).
- Where the FSD states a rule explicitly without a WA tag, that rule is also used, and the difference is listed separately (§2.2).
- Otherwise 07's default is used.

---

## 1. Values in use

**Column meanings**

| Column | Meaning |
|---|---|
| **Source** | `WA-nn` = FSD working assumption. `FSD <id>` = explicit FSD requirement without a WA tag. `07` = our recommended default. |
| **Confirmed by** | The question in **our** questionnaire that will confirm it, or **internal** if the client won't be asked. The FSD's own questionnaire references are listed in §2.3; they use a different numbering. |
| **Setting** | The runtime setting key (§3), or ⛔ **structural** if it can't be a setting (§4). `product:` means a per-product-version parameter whose default comes from the setting. |

### 1.1 Management

| 07 ID | Topic | Value in use | Source | Confirmed by | Setting |
|---|---|---|---|---|---|
| Q-M1 | Investment model | One open-ended running balance per investor, one flat rate, interest paid out monthly. Fixed-term placements are a later optional product (FSD INV-11, "Could"). | WA-02 | B1 | ⛔ structural |
| Q-M1b | Savings product | None | 07 | B2 | ⛔ structural |
| Q-M2 | Numbering | `ACL-000001` investor codes unchanged. Party `P-0000001`. Loan account 11 digits `BBBPPPNNNNN`. MCA `BBB900NNNNN`. | 07 | I11 | `numbering.*` (locked after first use, §4) |
| Q-M3 | Customer portal / app | None in this release | FSD §1.2 out of scope | I10 | ⛔ structural |
| Q-M4 | Branches | One branch: `000 Head Office` | 07 | A1 | reference data (`branches` table) |
| Q-M5 | Second-person approval for party / investor changes | **Identity, bank and payout details** need maker-checker. Other contact changes (phone, address, **email**) save immediately and are audited. New investors are created immediately with KYC "pending". | **WA-01** / FSD KYC-08 | B4 | `kyc.maker_checker_fields` |
| Q-M6 | Legal entities | Single entity | 07 | A2 | ⛔ structural |
| Q-M7 | Existing investors that are organisations | All migrated as persons. Investor relations reviews a generated list and reclassifies before migration. | 07 | B3 | internal migration step |
| Q-M8 | Loan approval limits | Up to KES 500,000: **credit manager**. 500,001–2,000,000: **credit committee, any 2 members**. Above 2,000,000: **board credit committee**. Credit officers prepare but don't approve. | **WA-14** / FSD §15 | D1, D2 | `approval_policies` (structured, §3.5) |
| Q-M8b | Other approval limits (no FSD value) | Withdrawals: any admin ≤ KES 1,000,000, finance manager above. Disbursement: finance officer ≤ 2,000,000, finance manager above. Manual journals: finance manager. | 07 | D1 | `approval_policies` / `transaction_limits` |
| Q-M8c | Write-off approval | Credit committee, any amount | WA-11 | D1 | `approval_policies` |

### 1.2 Credit

| 07 ID | Topic | Value in use | Source | Confirmed by | Setting |
|---|---|---|---|---|---|
| Q-C1 | Mandatory KYC fields | Individuals: name, ID/passport, KRA PIN, DOB, mobile, physical address, next of kin. Companies: legal name, reg. no., KRA PIN, registration date, ≥ 1 director with ID, phone, physical address. | 07 | C8, C9 | `kyc.required_fields.person`, `kyc.required_fields.organisation` |
| Q-C2 | Starting products | Three products, **all reducing balance**: (1) **business loan**: equal monthly instalments, 3–24 months, security title/logbook/guarantee, fees processing, CRB, legal; (2) **short-term bridge loan**: monthly interest, **principal at maturity**, 1–3 months, fees processing, CRB; (3) **asset finance**: equal monthly instalments, 6–36 months, logbook in joint names + tracker, fees processing, valuation, tracking (monthly), insurance. Rates and limits "set by management" (placeholders until C1). | **WA-04** / FSD §7.1 | C1, C3 | `product_versions` (structured) |
| Q-C3 | Arrears bands | Normal 0–30, Watch 31–90, Substandard 91–180, Doubtful 181–360, Loss > 360 days past due | WA-09 | E2 | `classification_sets` (structured) |
| Q-C3b | Interest to suspense | From **91 days** past due (normal and penalty interest). Released to income when paid. | WA-07 / FSD INT-04 | E1 | product: `classification_set.suspense_from_dpd` |
| Q-C4 | Fixed vs variable rates | Fixed only. Per-loan negotiated rate within product limits under maker-checker (FSD PRD-04). | 07 + FSD PRD-04 | C2 | product: `rate_type` (variable disabled) |
| Q-C5 | Letter templates | We draft offer letter, fee schedule, demand and clearance letters for legal approval. Replaced by Anchorstone's templates when supplied (FSD ORG-05). | 07 | C10 | `notification_templates` / document templates (structured) |
| Q-C6 | Fee treatment | Processing, CRB, legal, search, valuation: **deducted at disbursement**, income. Tracking: **monthly**, billed, pass-through. **Insurance premium: monthly**, billed, pass-through. Risk fund (if used): deducted, pass-through. | 07, adjusted to FSD INT-06 | C3 | product: `fee_definitions` |
| Q-C7 | Part-payments | Reduce future instalments, keep maturity date | 07 | C4 | product: `prepayment_rule` |
| Q-C7b | Early settlement | Interest to settlement date **plus one month's interest** | WA-08 / FSD REP-06 | C5 | product: `early_settlement_rule` |
| Q-C8 | "Confirm all" on AI review | Allowed for high-confidence fields with no failed validator or cross-check. Never for ID numbers, KRA PINs or amounts. | 07 | H2 | `ai.review.bulk_confirm_allowed`, `ai.review.bulk_confirm_min_confidence`, `ai.review.never_bulk_fields` |
| Q-C9 | "Suspend interest but still charge" | Manual move to suspense with approval (income stops, amount still owed) | 07 | internal | ⛔ structural (an approval workflow, not a value) |
| Q-C10 | Open-loan limit | Max **3** open loans per client **and** per related-party group | WA-05 / FSD ORG-10 | C7 | `lending.max_open_loans_per_client`, `lending.max_open_loans_per_group` |
| Q-C11 | AI accuracy gate | IDs, KRA PINs and registration numbers ≥ 99% exact; names ≥ 97%; statement amounts ≥ 98%. Credit manager signs off. | 07 | H5 (sign-off); thresholds internal | `ai.eval.thresholds` |

### 1.3 Finance

| 07 ID | Topic | Value in use | Source | Confirmed by | Setting |
|---|---|---|---|---|---|
| Q-F1 | Chart of accounts | Skeleton in 03 §2 until the accountant's list arrives | WA-13 | F1 | `gl_accounts` (structured) |
| Q-F2 | Day count | **Actual/365**: every calendar day accrues (including 29 Feb) and the annual rate is divided by 365. The same as investor interest today. | FSD INT-01 + 07 (see §2.2 note) | C6 | product: `day_count` (default `ACT/365F`) |
| Q-F3 | Provisioning | Bucket rates Normal 1%, Watch 3%, Substandard 20%, Doubtful 50%, Loss 100%, until the auditors approve a method (possibly IFRS 9 ECL) | WA-09 | E3 | `classification_sets` (structured) |
| Q-F4 | Bank mapping for history | By method: bank transfer → main bank account, M-Pesa → paybill float, cheque → clearing, cash → cash on hand. Staff pick the receiving account on new deposits. | 07 | F2 | `company_bank_accounts` + `gl.backfill.method_account_map` |
| Q-F5a | Investor interest accrual | Posted at approval, dated period end. The month closes only after approval. No estimate. | 07 + FSD §13.1 | F3 | `gl.investor_interest_month_end_estimate` (default false) |
| Q-F5b–d | NPL accrual policies | (b) Accrued-unpaid interest moves to suspense on transition: yes. (c) Reversed back on return to performing: yes. (d) Late corrections dated today for closed periods: yes, finance-approved. | 07 | internal | `gl.move_accrued_to_suspense_on_npl`, `gl.reverse_suspense_on_upgrade`, `gl.allow_late_corrections` |
| Q-F6 | Commission withholding tax | Agents 10%, staff through payroll (outside the system) | 07 | F6 | `commission.agent_wht_rate` |
| Q-F7 | Budgets | Annual, per GL account × branch × month, Excel import | 07 | F7 | ⛔ structural (feature, not value) |
| Q-F8 | Trade-finance accounting | Memo (off-balance-sheet) contingent entries. Trade finance is a later wave (FSD TRF-01 "Could"). | 07 | F8 | posting rules (code) |
| Q-F9 | External accounting package | None. Report from this system with TB and journal exports. | 07 | F5 | ⛔ structural |
| Q-F10 | Fee income recognition | At disbursement, with fees tagged "integral" so deferral (FSD §13.1 "or deferred fees") can be switched on | 07 + FSD §13.1 | F4 | `gl.defer_integral_fees` (default false) |
| Q-F11 | Exceptions vs EOD | EOD always runs and lists exceptions. Only **EOM close** is blocked. | 07 | D5 | `eod.block_eom_on_open_exceptions` (default true), `eod.block_eod_on_open_exceptions` (default false) |

### 1.4 Compliance

| 07 ID | Topic | Value in use | Source | Confirmed by | Setting |
|---|---|---|---|---|---|
| Q-CO1 | Lawful basis / consent | KYC: legal obligation. AI processing: consent, with a manual path. Marketing: consent. Confirmed data stays under KYC basis if AI consent is withdrawn. | 07 + FSD AI-01 | G3 | ⛔ structural (consent purposes) + `consent.notice_version` |
| Q-CO2 | Data location | Closest region approved by the DPO. Cloud processing outside Kenya allowed only once confirmed (FSD §5.4). AI go-live is gated on it. | 07 + FSD §5.4 | G1 | ⛔ structural (hosting) + `ai.enabled` gate |
| Q-CO3 | Out-of-portfolio access | Flag (log + report), don't block, except staff accounts and PEPs. Every document view logged (FSD SEC-06). Watermark KYC downloads. | 07 + FSD SEC-06 | D4 | `access.out_of_portfolio_mode` (`flag` / `block`), `documents.watermark_kyc` |
| Q-CO4 | In duplum | Flag and stop accrual when unpaid interest and charges reach outstanding principal | 07 = FSD INT-05 | E5 | `lending.in_duplum_enabled` |
| Q-CO5 | Credit bureau | Monthly submission to the bureau(s) Anchorstone uses; enquiries need consent | 07 = FSD NTF-05 | G7 | `crb.providers`, `crb.submission_day` |
| Q-CO6 | Screening lists | Internal blacklist + UN sanctions list + manual PEP flag. A match blocks onboarding until a manager reviews (FSD KYC-06). **In use: internal blacklist + PEP list only** (`screening.lists_enabled` = `internal_blacklist`, `pep`). The UN Security Council consolidated list is imported daily (01:00 Nairobi) from the published XML; the import and `sanctions_un` screening stay **off** until compliance confirms the source and refresh. | 07 + FSD KYC-06 | G6 | `screening.lists_enabled`, `screening.un_sanctions.import_enabled`, `screening.un_sanctions.source_url` |
| Q-CO7 | Notice wording approval | Legal approves recovery templates before use. Admins edit templates (FSD NTF-02) under maker-checker. | 07 + FSD NTF-02 | E6 | `notification_templates` (structured) |
| Q-CO8 | Retention | **Documents: 7 years after the relationship ends**, including declined applicants (the relationship ends at the decision). Raw AI outputs: 24 months after decision. Screening runs and audit logs: 7 years. | **WA-12** (documents) + 07 (AI outputs, logs) | G5 | `retention.documents_years_after_end`, `retention.ai_raw_output_months`, `retention.audit_years` |
| Q-CO9 | ID photos | Store ID images for KYC. Never analyse faces. | 07 | G8 | ⛔ structural (safety rule, §4) |
| Q-CO10 | Age in pre-selection | **18 to 70 at loan maturity**, else Not qualified | **WA-10** / FSD §5.3 | H4 | screening rule set (structured) |

### 1.5 IT

| 07 ID | Topic | Value in use | Source | Confirmed by | Setting |
|---|---|---|---|---|---|
| Q-IT1 | Hosting | Managed cloud, PostgreSQL with point-in-time recovery | 07 | I1 | ⛔ structural (infrastructure) |
| Q-IT2 | Removing staff accounts | Disable only, never delete | 07 | I7 | ⛔ structural (code change: remove the delete endpoint) |
| Q-IT3 | Backups | Managed PITR + daily OneDrive copy (FSD NTF-07). Quarterly restore drill. | 07 + FSD NTF-07 | I2 | env config (`DB_BACKUP_*`) |
| Q-IT4 | Passbook | None. PDF statements. | 07 | I12 | ⛔ structural |
| Q-IT5 | Password policy | Minimum length **10** (satisfies the FSD's "at least 8"; see §2.1 #5). **No reuse of any previous password.** **Change every 90 days.** Lock after **5 failed attempts in 15 minutes** (already in place). Idle logout 30 min. Single session optional. | **FSD SEC-02** + 07 | I6 | `security.password_min_length` (floor 8), `security.password_history` (0 = all), `security.password_max_age_days`, `security.login_max_failures`, `security.login_window_minutes`, `security.login_lock_minutes`, `security.login_ip_max_failures` (20 failures from one IP in the window), `security.idle_timeout_minutes`, `security.single_session` |
| Q-IT6 | BI tool | Read-only replica + Power BI / Metabase | 07 | I8 | ⛔ structural |
| Q-IT7 | SMS provider | Africa's Talking behind our adapter | 07 + FSD NTF-04 | I4 | env config (provider credentials) + `sms.sender_id` |
| Q-IT8 | Lending book source | Full extract at an agreed cutoff, migration audit, rehearsals during the lending build (FSD §19) | 07 = FSD §19 | I5 | ⛔ structural |
| Q-IT9 | Upload formats | PDF, JPEG, PNG, HEIC (converted), TIFF; max 25 MB | 07 | I9 | `documents.allowed_types`, `documents.max_mb` |
| Q-IT10 | System admin approvals | No business approval rights for super admin (IT) | 07 = FSD §15 | D3 | role definitions (structured, SoD rule fixed) |
| Q-IT11 | M-Pesa | C2B paybill for repayments. **Payouts by M-Pesa B2C and bank file** (FSD NTF-06, "Should"). | 07 + **FSD NTF-06** | I3 | `payments.b2c_enabled` (feature flag, needs build) |
| Q-IT12 | Volumes | 20,000 parties, 10,000 active loans, 2,000 receipts/day, 3,000 documents/month, 50 concurrent staff | 07 | A3, H6 | internal (load-test targets); `ai.budget.monthly_usd` |

### 1.6 FSD working assumptions with no matching question in 07

| WA | Value in use | Confirmed by | Setting |
|---|---|---|---|
| WA-03 | Withholding tax on investor interest 0%, hidden on statements | B5 | `investments.wht_rate_percent` (today the constant `DEFAULT_TAX_RATE_PERCENT`) |
| WA-06 | Penalty interest on overdue amounts from **7 days** past due. Rate per product (none set yet). | E4 | product: `penalty_grace_days` (global default `lending.penalty_grace_days` = 7, product override), `penalty_rate` |
| WA-10 | Pre-selection rules (10): time in business ≥ 12 months (else Not qualified); average monthly inflows (6 months) ≥ 3 × instalment (else Needs review); CRB: listed → Not qualified, cleared → Needs review; forced-sale cover ≥ 125% (else Needs review); age 18–70 at maturity (else Not qualified); name/ID consistency (else Needs review); CR12 directors match (else Needs review); bounced items ≤ 2 in 6 months (else Needs review); other lenders' repayments < 50% of inflows (else Needs review); **collateral owner is the applicant or a guarantor (else Needs review; secured products only), added 2026-10-18 as rule 10** | H3, H4 | `screening.rule_set` v2 (10 rules; v1 had the first 9) (rules as data; changed through settings.change, each run records the version) |
| — (FSD NTF-01) | Repayment reminders **3 days before** and on the due date; missed payment, receipt, disbursement, insurance expiry, statements | internal | `notifications.reminder_days_before` (default [3, 0]) |
| — (FSD REP-02) | Allocation order: penalty → interest → principal. Disposal proceeds: principal → interest → penalty. | internal | product: `allocation_order`, `disposal_allocation_order` |
| — (FSD SEC-04) | Restrict sign-in times per user; block users on leave | internal | `access_windows` (structured) |
| — (internal) | Email sending: **3 attempts** before a queued email is marked failed | internal | `email.max_attempts` |
| — (phase 3a) | AI reads documents with **Claude Opus 5.5** (`claude-opus-5-5`) at effort `medium`; 3 tries per call; list prices Opus 5.5 $4 / $20, Sonnet 5.5 $2 / $10, Haiku 5.5 $0.10 / $0.50 per million input / output tokens | H5, H6 (model chosen with the client 2026-10-17; accuracy sign-off still due) | `ai.model_extract` (2 approvers), `ai.effort`, `ai.max_attempts`, `ai.price_table` |
| — (05 §6.2) | Statement keywords, whole words, any case; each match records the keyword it hit. **Other lenders (v2, 49 phrases, TO BE EXTENDED BY CREDIT):** banks' loan narrations (LOAN REPAYMENT, LN REPAYMENT, LOAN INSTALMENT, OD LOAN REPAYMENT, KCB / EQUITY / CO-OP / NCBA / ABSA / STANBIC / DTB / I&M / FAMILY BANK LOAN …), mobile-loan products (FULIZA, M-SHWARI LOAN, KCB M-PESA LOAN, EAZZY LOAN, MCO-OP CASH, TIMIZA, HUSTLER FUND, STAWI …), digital lenders (TALA, BRANCH INTERNATIONAL, ZENKA, OKOLEA, ZASH, M-KOPA, WATU CREDIT, MOGO, PLATINUM CREDIT …) and microfinance banks (KWFT, FAULU, MUSONI, SMEP, LETSHEGO). Loan-specific phrases only: a bare M-SHWARI would count savings deposits. **Bounced / returned:** RTD, UNPAID, RETURNED, INSUFF, DISHON, BOUNCED. | H3 (credit to extend the lender list) | `ai.statements.lender_keywords`, `ai.statements.returned_item_keywords` |
| — (phase 3) | AI spending limits: **US$20 a month**, **US$2 per application**, **US$3 per reading** (also caps test runs). Each call's cost is estimated from its pages and the model's price before it is made, and refused if it would pass a limit; spend counts actual costs. Circuit breaker: pause after **5** failed calls in a row or **more than 10 in 10 minutes**; admins alerted; an admin resumes | H6 (budget); breaker internal | `ai.budget.monthly_usd`, `ai.budget.per_application_usd`, `ai.budget.per_run_usd`, `ai.breaker.*` |
| — (phase 3b) | AI values read with confidence below **0.85** are highlighted on the review screen; every value still needs an explicit accept or correct | H2 | `ai.review.confidence_threshold` |

---

## 2. Where 07 and the FSD disagree (FSD value is used)

### 2.1 Conflicts with a WA value or an explicit FSD rule

| # | 07 ID | 07 recommended | FSD value now in use | Notes |
|---|---|---|---|---|
| 1 | Q-M8 | Credit **officer** ≤ 500k; credit manager ≤ 2M; committee (2 of 3) above | **WA-14**: credit **manager** ≤ 500k; credit committee (any 2) 500,001–2M; **board credit committee** above 2M | Adds a third tier (board committee). Credit officers can't approve at all. ⚠ **Our questionnaire D1 is pre-filled with the 07 values** and should be updated before it goes to the client. |
| 2 | Q-C2 | Business loan, short **bullet** working-capital loan (everything at the end), **check-off** loan | **WA-04**: business loan, short-term **bridge loan with monthly interest and principal at maturity**, **asset finance**. All reducing balance. | Check-off drops out of the starting set (it's still supported by the engine, FSD PRD-05 "Should"). Asset finance comes in, which brings tracking and insurance fees and joint-name logbooks from day one. |
| 3 | Q-M5 | Maker-checker on identity, payout **and the statement email** | **WA-01 / KYC-08**: identity, bank and payout only. **Email changes save immediately** (audited). | ⚠ Control weakness worth raising with the client: changing an investor's email redirects their statements without a second check. Kept as a setting (`kyc.maker_checker_fields`), so adding `email` back is a settings change. |
| 4 | Q-CO8 | Declined-application documents kept **24 months** | **WA-12**: documents kept **7 years after the relationship ends**, applied to every document including declined applicants | ⚠ Longer retention of declined applicants' data may conflict with the DPA's minimisation principle. Raised for the DPO (G5). Raw AI outputs stay at 24 months (WA-12 covers documents only). |
| 5 | Q-IT5 | No forced expiry; history of last 5 passwords | **FSD SEC-02**: **change every 90 days**; **no reuse** (any previous password); at least 8 characters; lock after 5 failed in 15 min | Expiry and full no-reuse adopted. **Minimum length stays 10.** The FSD says "at least 8", which 10 satisfies, and lowering the current enforced 10 would weaken existing accounts. If you want the literal 8, it's a one-line settings change (floor 8). |
| 6 | Q-IT11 | No M-Pesa payouts; bank transfer only | **FSD NTF-06**: pay out via **M-Pesa B2C** and bank file ("Should") | B2C needs Daraja B2C credentials and a build item. Recorded as a feature flag, off until built. |
| 7 | Q-C6 | Insurance premium **deducted at disbursement** | **FSD INT-06 / WA-04**: insurance premium **monthly** | Asset-finance insurance is billed monthly and passed through to the insurer. |

### 2.2 Conflicts with other architecture documents (not 07)

| # | Where | Our design said | FSD says (now used) | Effect |
|---|---|---|---|---|
| 8 | 06 phase 7 AC 7 | Reminders **7 days** before, on due date, arrears | **NTF-01**: **3 days** before and on the day | Setting default changed to [3, 0]. Phase 7 acceptance criteria should follow the setting. |
| 9 | 03 §4.4 | Waterfall penalty → interest → **fees** → principal | **REP-02**: penalty → interest → principal (fees not mentioned) | Fees are placed **between interest and principal** (FSD silent on fees; this matches its intent of clearing charges before principal). Flagged for credit to confirm. |
| 10 | 03 §4.2 | Disbursement credits the **member collection account**, fees deducted from it, net paid Bank | **§13.1**: Dr Loans receivable (gross) / Cr **Bank (net)** and Cr Fee income **or deferred fees** | Same net effect on the GL. The MCA is our subledger choice for liens, overpayments and suspense. Kept, since it's structural (§4). The FSD's "or deferred fees" option is covered by `gl.defer_integral_fees`. |
| 11 | 05 / 06 phase order | CRB integration in phase 10 | **WA-10** pre-selection uses **CRB status** from day one | Until the CRB integration exists, staff enter the CRB result manually on the application (a confirmed field like any other). The rule reads that field. |
| 12 | 07 Q-F2 | "ACT/365F" | **INT-01**: "actual/365, with leap years respected" | ⚠ **Ambiguous, not a conflict.** Read as actual days accrue, including 29 Feb, divided by 365 (= ACT/365F, the same as investors today). If the client means 366 in leap years, it's a product setting change. Our questionnaire C6 asks exactly this. |

### 2.3 The FSD's questionnaire references don't match our questionnaire

The FSD's Section 20 cites a "Requirements Questionnaire" whose numbering differs from `deliverables/Anchorstone-Client-Questionnaire.docx`.

| WA | FSD cites | Our question | Match? |
|---|---|---|---|
| WA-01 | B3 | B4 | ✗ (our B3 is organisation investors) |
| WA-02 | B1 | B1 | ✓ |
| WA-03 | B5 | B5 | ✓ |
| WA-04 | C1 to C3 | C1, C3 | ≈ |
| WA-05 | C5 | C7 | ✗ (our C5 is early settlement) |
| WA-06 | F1, F2 | E4 | ✗ (our F1/F2 are chart of accounts and bank accounts) |
| WA-07 | F4 | E1 | ✗ |
| WA-08 | C4 | C5 (and C4) | ≈ |
| WA-09 | F3 | E2, E3 | ✗ |
| WA-10 | D1 to D4 | H3, H4 | ✗ (our D is approvals) |
| WA-11 | F6 | D1 | ✗ |
| WA-12 | H5 | G5 | ✗ |
| WA-13 | G1 | F1 | ✗ |
| WA-14 | E1 | D1 | ✗ |

**Decision needed:** one questionnaire must be the one sent to the client, and the FSD's Section 20 references should then be updated to match it. Until then, the "Confirmed by" column in §1 uses **our** numbering.

---

## 3. Runtime settings design

### ADR-08-1 — A versioned, effective-dated settings registry, changed only through maker-checker

**Context.**
- Every value in §1 is provisional, and the client's answers will change many of them.
- Today several are hard-coded constants:
  - `MIN_PASSWORD_LENGTH = 10` in `app/Admin/route.py`;
  - `DAY_COUNT = 365` and `DEFAULT_TAX_RATE_PERCENT = 0` in `app/Interest/service.py`;
  - `MAX_ATTEMPTS = 3` in `app/Emails/model.py`;
  - `MAX_RECIPIENTS` in `app/Emails/statements.py`.
- Others live in environment variables (`LOGIN_*` in `config.py`). Changing any of them is a code change or a redeploy, and leaves no business audit trail.
- These are business rules in a regulated firm. Who changed a rule, when, why, and with whose approval must be provable, and past calculations must stay reproducible.

**Options considered**

| Option | Assessment |
|---|---|
| A. Constants in code | Every client answer becomes a deployment. No audit of business rule changes. |
| B. Environment variables | No history, no maker-checker, and they apply instantly (including retroactively to recalculations). |
| C. A mutable `settings` table | No history. A recalculation of last month uses this month's rule. |
| D. **Code-defined registry (key, type, validator, default, binding) + DB table of immutable, effective-dated versions, changed through `change_requests`** | Every change is approved, audited and dated, and any past value can be retrieved as of a date. |

**Decision.** **Option D.**
- **Simple values** (numbers, booleans, lists, small objects) live in the registry.
- **Rich, already-versioned business configuration** keeps its own tables and follows the same rules:
  - product versions;
  - classification sets;
  - screening rule sets;
  - approval policies and transaction limits;
  - interest rates;
  - notification templates;
  - GL accounts and mappings.

  The rules: maker-checker, immutable versions, effective dating, and a `source` tag (§3.4).

**Consequences**
- Client answers become change requests, not code.
- A "still on working assumptions" report becomes a go-live gate.
- Every place that reads a business value must call the settings service. A test enforces that no registered key is read any other way.

### 3.1 Registry (code: `backend/app/Settings/registry.py`)

The registry is the single list of setting keys. Each entry declares:

| Field | Meaning |
|---|---|
| `key` | Dotted name, e.g. `lending.max_open_loans_per_group` |
| `type` | `int` / `decimal` / `bool` / `enum` / `list` / `json` (with a JSON Schema) |
| `default` | The working-assumption value (§1). Seeded as version 1. |
| `validator` | Bounds and invariants, e.g. `password_min_length ≥ 8`, `0 ≤ wht_rate ≤ 100`, `reminder_days_before` sorted and ≥ 0 |
| `scope` | Which scopes may override: `global`, `branch`, `product` |
| `binding` | When the value attaches to a record (§3.3): `immediate`, `event_date`, `at_booking`, `new_versions_only` |
| `category` | `credit` / `finance` / `investments` / `compliance` / `security` / `operations` |
| `edit_permission`, `approve_permission` | e.g. `settings.credit.edit` / `settings.credit.approve`. System administrators can't approve non-IT categories (segregation of duties). |
| `approvals_required` | 1 by default. 2 for `security.*`, `ai.enabled` and `ai.model_extract`. (`kyc.maker_checker_fields` is planned at 2 but is 1 in the registry, pending confirmation.) |
| `wa_ref`, `questionnaire_ref`, `seventeen_ref` | Traceability back to this document |
| `description` | Plain-language text shown on the Settings screen |

Unknown keys are refused. A registry change (new key, changed type) is a code change with a migration, which is what we want for *shape*. *Values* are data.

### 3.2 Tables

| Table | Key fields |
|---|---|
| `setting_versions` | `id`, `key`, `scope_type` (`global` / `branch` / `product`), `scope_id` (nullable), `value` (jsonb, validated against the registry), `effective_from` (business date, Nairobi), `version_no`, `status` (`active` / `superseded` / `rejected`), `source` (`working_assumption` / `client_confirmed` / `internal_decision`), `evidence` (questionnaire answer ref, document ID or meeting note), `reason`, `change_request_id`, `created_by`, `approved_by`, `approved_at` |
| `change_requests` *(04 §1)* | `request_type = 'settings.change'`, payload `{key, scope, value, effective_from, source, evidence, reason}` |

**Database rules**
- **Immutable:** no UPDATE or DELETE on `setting_versions` (trigger). A change is a new version.
- **One value per date:** unique `(key, scope_type, scope_id, effective_from)`.
- **Locked months:** `effective_from` may not fall inside a closed GL period or an approved interest month, for keys with `event_date` binding. This is the same rule `set_rate()` applies to investor interest rates today.
- **Who can approve:** the approver can't be the maker (the 04 trigger). `approvals_required = 2` needs two distinct approvers.

### 3.3 Reading values, and when a change takes effect

```python
settings.get("lending.max_open_loans_per_group")                          # today, global
settings.get("penalty_grace_days", scope=("product", pv.id))              # product override → global default
settings.get("investments.wht_rate_percent", as_of=period.period_end)     # value in force on that date
```

**Resolution:**
1. Take the most specific scope with a version whose `effective_from ≤ as_of`.
2. Otherwise fall back to the next broader scope (product → branch → global).
3. Otherwise use the registry default. This only happens before seeding; a startup check refuses to run with unseeded keys.

**Caching:** values are cached per request, with a process-wide cache keyed by a `settings_epoch` counter that each approval bumps, so all workers pick up a change on their next request.

**Binding:**

| Binding | Meaning | Examples |
|---|---|---|
| `immediate` | The next action uses the new value | `security.login_max_failures`, `access.out_of_portfolio_mode`, `documents.max_mb` |
| `event_date` | Calculations use the value in force on the business date of the event, so re-running history reproduces it | `investments.wht_rate_percent`, `notifications.reminder_days_before`, retention periods (evaluated on the deletion date) |
| `at_booking` | The value is copied onto the record when it's created and never re-read | Open-loan limits (checked at booking), commission WHT (copied onto the commission row) |
| `new_versions_only` | Product-level defaults. Changing the global default affects **new product versions**; existing loans keep their product version (02 ADR-02-5). | `penalty_grace_days`, `day_count`, `allocation_order`, early-settlement rule |

**Consequence of `new_versions_only`.** If the client changes, say, the penalty grace period from 7 to 10 days:
1. Admin changes the setting (maker-checker).
2. Admin publishes new versions of the affected products (maker-checker).
3. **Existing loans keep 7 days** unless a separate, approved "re-price existing loans" action moves them to the new version.

That last step is a deliberate business decision, never a side effect.

### 3.4 Working assumption → confirmed

1. **Phase 2a seed migration:** every registry key gets version 1 with `source = 'working_assumption'`, `evidence = 'WA-nn'` or `'07 Q-xx'`, `effective_from` = go-live date. Structured config (products, rule sets, policies) is seeded the same way, with a `source` column added to each.
2. **When the client answers:** staff raise one change request per answered question:
   - "Confirm as is": a new version with the same value and `source = 'client_confirmed'`;
   - or "change to X".

   `evidence` holds the questionnaire ID (and, ideally, the uploaded signed questionnaire as a document).
3. **Settings → Business rules page:**
   - every key with its current value and a **Working assumption / Confirmed** badge;
   - pending changes awaiting approval;
   - full history with who and why;
   - a filter for "not yet confirmed".
4. **Go-live gate:** a report lists every value still `working_assumption`. Go-live for a wave needs each key in that wave's modules either confirmed or explicitly accepted by management (an `internal_decision` version with a reason).

### 3.5 Structured configuration (own tables, same rules)

| Config | Table (02 / 04 / 05) | Seeded from |
|---|---|---|
| Products, fees, day count, allocation, early settlement, penalty | `product_versions`, `fee_definitions` | WA-04, WA-06, WA-08, Q-C6, FSD INT-06, REP-02 |
| Arrears bands, suspense trigger, provision rates | `classification_sets`, `classification_buckets` | WA-07, WA-09 |
| Pre-selection rules | `screening_rule_set_versions` | WA-10 |
| Approval matrix and limits | `approval_policies`, `transaction_limits` | WA-14, WA-11, Q-M8b |
| Investor interest rate | `interest_rates` (exists) | Management |
| Message templates | `notification_templates` | Q-C5, Q-CO7, FSD NTF-02 |
| Chart of accounts, mappings | `gl_accounts`, `product_gl_mappings` | WA-13 |
| Branches | `branches` | Q-M4 |
| Sign-in windows | `access_windows` | FSD SEC-04 |

Each gains `source` and `evidence` columns, so the go-live report covers them too.

### 3.6 Settings vs environment

| Kind | Where | Examples |
|---|---|---|
| Business rules | **Settings registry / structured config** (this document) | Everything in §1 marked with a setting key |
| Secrets and infrastructure | **Environment** (unchanged) | `SECRET_KEY`, `DATABASE_URI`, `ANTHROPIC_API_KEY`, `AI_REQUEST_TIMEOUT_S`, SMTP and Daraja credentials, `TRUSTED_PROXY_COUNT`, backup credentials |
| Operational tuning | Settings, category `operations` | Email batch size and interval (already in `email_settings`, to be folded into the registry), AI concurrency and budgets |
| AI model and prices | Settings, category `ai` (phase 3a; replaces the `AI_MODEL_*` environment variables of ADR-05-2) | `ai.model_extract` (two approvers; a change still needs an accuracy run, 05 §12), `ai.price_table` |

The `LOGIN_*` values currently in `config.py` move to `security.*` settings. The environment values become the seed defaults for the migration only.

### 3.7 Tests the settings work must add

| Area | Tests |
|---|---|
| Registry | Every key has a default, a validator and a binding. Unknown keys refused. Invalid values refused (e.g. `password_min_length = 6`). |
| Maker-checker | The maker can't approve. Two-approval keys need two distinct people. A rejected request changes nothing. |
| Effective dating | `get(as_of=…)` returns the right version across a change. A version dated into a closed period is refused. Re-running a past interest month after a WHT change reproduces the stored result. |
| Binding | Changing `penalty_grace_days` doesn't change existing loans' product version. Changing `login_max_failures` takes effect on the next sign-in. |
| No hard-coded rules | A test fails if any registered key's former constant (`MIN_PASSWORD_LENGTH`, `DAY_COUNT`, `DEFAULT_TAX_RATE_PERCENT`, `MAX_ATTEMPTS` …) is still referenced outside the registry. |
| Go-live report | Lists exactly the keys and config rows with `source = 'working_assumption'`. |

---

## 4. What can't be a setting (structural decisions)

These choose **what the system is**, not a value inside it. Changing them needs design and code (and often a migration), so they're recorded as decisions with a phase, not as settings.

| Decision | Why it can't be a setting |
|---|---|
| **Investment model** (running balance vs term placements, Q-M1 / WA-02) and any savings product | Different tables (`placement_receipts`), posting rules, maturity processing and statements. Adding term placements is a new product kind. |
| **Single vs multi-entity** (Q-M6) | Entity would be a dimension on every account, journal and report, and needs inter-company postings. |
| **Currency** (KES only) | Turning on FCY needs revaluation postings, rate feeds and multi-currency reporting. The `CHECK (currency = 'KES')` is relaxed by a migration, not a toggle. |
| **Numbering formats** (Q-M2) | Settable **until the first number of that kind is issued**, then locked (printed on letters and used as M-Pesa references). `ACL-` investor codes are never settable. |
| **Customer portal** (Q-M3), **passbook** (Q-IT4), **BI replica** (Q-IT6), **external accounting export** (Q-F9) | Features to build, not values. |
| **Hosting and data location** (Q-IT1, Q-CO2) | Infrastructure and legal decisions. The application only has a gate (`ai.enabled`) that stays off until approved. |
| **Posting rules** (event → Dr/Cr lines) and **the member collection account design** (§2.2 #10) | Code, by ADR-03-5. Only the *account mappings* are configuration. |
| **Kinds of behaviour**: a new interest method, schedule type, fee treatment, allocation component, provisioning model (e.g. IFRS 9 ECL) | New calculation code. Settings choose *among* implemented kinds, never add one. |
| **Consent purposes** (Q-CO1) and **data-subject rights processes** | Legal design. The wording (`consent.notice_version`) is configurable. |
| **Approval workflows themselves** (e.g. Q-C9 "suspend but still charge", user deletion → disable-only Q-IT2) | Process code. Limits and policies are configuration. |
| **M-Pesa B2C payouts** (Q-IT11) | Needs an integration build. `payments.b2c_enabled` only switches on a built feature. |
| **Safety invariants**, deliberately *never* configurable | Money is Decimal; maker ≠ checker; posted records never edited or deleted; every action audited in the same transaction; balanced journals; closed periods refuse postings; the AI never decides; protected attributes (gender, marital status, religion, ethnicity, health) can't be used in rules; faces in ID photos are never analysed (Q-CO9); the password minimum can't drop below 8. These are in `CLAUDE.md` and enforced in code and in the database, so a settings screen can't switch off a control the regulator relies on. |
