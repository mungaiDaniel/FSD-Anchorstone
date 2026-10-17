# 06 — Phase plan (phases 2–13)

**Phase 1** (stabilisation, done October 2026) fixed the startup bug and added login protection, transactional audit, reversal notices and stored interest PDFs.

**Every phase ends with the `CLAUDE.md` definition of done:**
- full backend suite green;
- `npx tsc -b` and `npm run build` clean;
- new tests for every new behaviour, covering allowed **and** refused paths (wrong role or permission, maker = checker, invalid input, locked period, duplicates);
- migrations reviewed;
- docs updated.

The acceptance criteria below are *in addition* to that.

---

## Recommended ordering changes (summary)

| # | Change | Why |
|---|---|---|
| 1 | **Split phase 2** into **2a Foundations** (branches, RBAC, maker-checker framework, job queue/worker, document store, audit immutability) and **2b Party/KYC** | Every later module needs these. Bolting maker-checker or permissions on after five modules exist means rewriting them. 2a is invisible to users, so it can ship alone safely. |
| 2 | **Pull the business-date/EOD *framework*** (`business_days`, `batch_runs`, resumable steps) **from phase 12 into phase 6** | Daily interest accrual (phase 6) can't run safely without idempotent, resumable, catch-up runs. Phase 12 keeps EOM/EOY close automation, performance and DR. |
| 3 | **Phase 3 (AI) creates a minimal application shell** that phase 5 extends | Pre-selection needs an application to attach documents and results to. Phase 5 then adds products, credit decisions and disbursement to the same table. No rework. |
| 4 | **Phases 3 (AI) and 4 (GL) are independent** after 2b | Both depend only on parties, documents and jobs. With two developers they can run in parallel. With one, keep 3 → 4 if management wants AI pre-selection early (credit can use it while loans are still booked in the old system). Otherwise do **4 first**, because the GL de-risks the live investor book. *Default: keep the given order.* |
| 5 | **Build the notification channel abstraction (email + SMS) in phase 7**, not 10 | Repayment reminders, arrears and insurance-expiry notices (phases 7–8) need SMS. Phase 10 keeps CRB, M-Pesa B2C (if any), bank statement import and API hardening. |
| 6 | **Start migration rehearsals at the end of phase 5** and repeat after phases 6, 7 and 8 | The FSD's lending book comes from another system (Q-IT8). Finding mapping problems in phase 13 is too late. Phase 13 keeps the final cutover and UAT. |
| 7 | **Minimal watchlist screening and consent capture move into phase 2b** | Onboarding without blacklist/PEP screening isn't acceptable for a lender, and AI processing (phase 3) can't start without recorded consent. Full AML monitoring stays in phase 11. |
| 8 | **Two go-live waves** (§ end) | Investments-on-GL plus party/KYC plus AI pre-selection can go live before the full lending stack, reducing big-bang risk. |

---

## Phase 2a — Foundations

| | |
|---|---|
| **Goal** | Put in the cross-cutting machinery every module uses, with no visible change to investors. |
| **Dependencies** | Phase 1. Spike decision on Procrastinate vs an in-house queue (ADR-04-3). Q-IT1 (hosting) for the storage backend. |
| **Main tables** | `branches`; `departments`, `roles`, `permissions`, `role_permissions`, `user_roles`, `user_branch_scopes`, `transaction_limits`, `sod_conflicts`; `change_requests`, `change_request_events`, `approval_policies`; job queue tables; `documents`, `document_links`, `data_access_logs`; `number_sequences`; `password_history`. Adds `branch_id` to `users`. |
| **Work** | `@requires(permission)` with the old decorators aliased; built-in bundles reproduce today's three roles exactly; Approvals inbox UI (backend + page); `DocumentStore` (local + Azure Blob) with envelope encryption, virus scan, streaming download with access logging; worker process; email drain, AUM report and backups moved off APScheduler; immutability trigger on `audit_logs`; user hard-delete replaced by disable (Q-IT2). |

**Acceptance criteria**
1. With built-in bundles, every existing endpoint returns the same status for `user`, `admin` and `super_admin` as before. The existing 80+ tests pass unchanged.
2. A user without a permission gets 403 on its endpoint. A user granted the permission through a new custom role gets 200 (parametrised over every endpoint).
3. A change request approved by its maker is rejected **by the database trigger** (test bypasses the service layer). An approval above the approver's `transaction_limits` routes to the next policy level. A stale `base_version` fails with the documented message.
4. Starting 4 web workers produces exactly **one** scheduled backup and one AUM generation per period. Email jobs are never sent twice (test with concurrent workers).
5. A document uploaded through the API is stored encrypted: the blob bytes don't contain the plaintext, and the SHA-256 of the decrypted bytes matches. Download without `document.view` → 403. Every download writes a `data_access_logs` row. Destroying the wrapped key makes the content unrecoverable.
6. `UPDATE` / `DELETE` on `audit_logs` fails at the database.
7. Role, limit and scope changes are themselves change requests requiring a second system administrator.

## Phase 2b — Parties, KYC, investor migration

| | |
|---|---|
| **Goal** | One party per real person or company, with KYC, documents, consent, screening and the 360 view. Existing investors moved onto it invisibly. |
| **Dependencies** | 2a. Q-M2 (numbering), Q-M4 (branch list), Q-M5 (maker-checker on investor edits), Q-M7 (existing investors who are organisations), Q-C1 (mandatory KYC fields). Pre-flight duplicate report resolved by investor relations. |
| **Main tables** | `parties`, `party_persons`, `party_organisations`, `party_identifiers`, `party_contacts`, `party_addresses`, `party_bank_accounts`, `party_roles`, `party_relationships`, `party_mandates`, `party_consents`, `watchlist_entries`, `screening_results`, `accounts` (investment type), `account_holds`; `investors.party_id` / `account_id`. |
| **Work** | Party CRUD through change requests per policy; duplicate detection (exact identifiers block, phone/name warn); merge with maker-checker; next of kin, directors, signatories, guarantors as related parties; consent capture (purposes incl. AI); internal blacklist, PEP flag and UN sanctions list import with screening at onboarding; party 360 page; investor creation goes through the party (existing party reused); pending withdrawals become `account_holds`. |

**Acceptance criteria**
1. Migration on a copy of the demo DB: every investor has exactly one party and one investment account with `account_no = client_code`. Counts match.
2. **Golden-file test:** `/investors`, `/investors/<id>`, ledger, statements (PDF text) and all 7 Excel reports are identical before and after migration.
3. The migration refuses to run while the pre-flight report finds duplicate ID numbers or KRA PINs.
4. Creating a second party with an existing (normalised) national ID or KRA PIN fails with a message naming the existing party number. Same phone → warning only.
5. Editing a party's ID number creates a change request. The party is unchanged until a different user approves.
6. Adding an investor for an existing borrower or guarantor party attaches the investor role. No second party is created. `ACL-` code allocation is unchanged.
7. Onboarding a party whose name or identifier matches a watchlist entry stores a `screening_results` row and blocks KYC verification until reviewed.
8. A party with no `ai_document_processing` consent can't have AI jobs enqueued (tested at the job layer).
9. A pending withdrawal reduces available balance through `account_holds`, with the same results as today's `pending_withdrawals_total` across the existing withdrawal tests.

## Phase 3 — AI document pipeline and pre-selection

> **Temporary in phase 3b.** The pre-screen application (`loan_applications`: three WA-04 products, term limits,
> indicative rate) and its **estimated** instalment (`app/Applications/estimate.py`: reducing balance, interest-only
> for the bridge loan) exist only so pre-selection has something to attach to. Phase 5's product engine replaces the
> product list, the term limits and the estimate with versioned products and real schedules. The application table
> and its links stay and are extended. Screens and API responses label the instalment "estimate" until then.

| | |
|---|---|
| **Goal** | Extract data from scanned client documents, have staff confirm it, compute metrics in code and run versioned rules → Shortlisted / Needs review / Not qualified. |
| **Dependencies** | 2b (parties, consent, documents, jobs, maker-checker). Compliance items §9.6 of 05 (**DPIA sign-off is a go-live gate, not a build gate**). Q-C8, Q-C11, Q-CO9, Q-CO10. Anthropic account, key and processor terms. |
| **Main tables** | `loan_applications` (shell: applicant, requested amount and tenor, product code as text until phase 5, status), `application_parties`, `extraction_jobs`, `extraction_pages`, `extraction_calls`, `extracted_fields`, `extracted_transactions`, `field_reviews`, `screening_rule_sets`, `screening_rule_set_versions`, `screening_rules`, `screening_runs`, `screening_rule_results`, `computed_metrics`, `ai_usage_monthly`. |
| **Work** | `DocAI` module (client, preprocess, classify, extract, validators, M-Pesa parser + 1–2 bank parsers, schemas and prompts for all 12 document types); review screen with maker-checker; cross-document checks; metrics registry; rules editor with validation, backtest and publish; screening run and override; cost tracking and budgets; evaluation harness. |

**Acceptance criteria**
1. **No code path outside `app/DocAI/client.py` imports the Anthropic SDK** (test). The API key never appears in any API response, log line or frontend bundle (test scans responses and `dist/`). The model comes only from configuration, and startup fails if it's missing while AI is enabled.
2. For each document type, a recorded response that violates the schema triggers exactly one repair attempt, then manual entry. A valid response stores every field with confidence and source page (missing `source_page` → validation failure).
3. A bank statement with one deliberately mis-read amount is flagged by row-level balance arithmetic. One with a missing page is flagged by page continuity. Neither can feed metrics until resolved.
4. Metric functions match hand-calculated fixtures to the cent (including own-account transfers excluded, reversals, returned items).
5. Cross-document checks: an ID number differing between ID and application → `fail`. CR12 with an extra director not captured at onboarding → `fail`, listing that director. Logbook owner = guarantor → `pass`.
6. Extracted values reach `party_identifiers` only after a reviewer confirms **and** a different user approves. Reviewer = approver is refused.
7. Rules referencing a protected attribute can't be published. A published rule set version can't be modified (DB trigger). Screening stores the version ID. `screening replay` reproduces every stored outcome.
8. Any `not_qualified` rule failure → Not qualified. Any missing input → Needs review. A Not qualified application can't move to credit analysis without an override reason approved by a second user.
9. API 429/5xx is retried with backoff and then the job is marked failed with a Retry action. The circuit breaker pauses the queue after the configured error rate. The per-application budget stops further calls pending admin approval.
10. Retention job (dry run) lists declined-application documents older than the configured period.

## Phase 4 — General ledger and investor migration onto the GL

| | |
|---|---|
| **Goal** | Double-entry GL with DB-enforced invariants. Investor business posting to it, reconciled to the cent. |
| **Dependencies** | 2a (branches, maker-checker, jobs), 2b (accounts). Q-F1 (chart of accounts), Q-F4 (bank account mapping), Q-F5 (accrual options), Q-F9 (external package). |
| **Main tables** | `gl_accounts`, `gl_periods`, `journal_entries`, `journal_lines`, `journal_drafts`, `journal_draft_lines`, `product_gl_mappings` (investment product), `company_bank_accounts`, `account_balance_snapshots`; `journal_entry_id` columns on deposits, withdrawals and interest tables. |
| **Work** | Triggers (balanced, immutable, period, control-account, never-negative); posting engine with the 03 §4.1 rules; `ledger.py` source switch (`legacy` / `shadow` / `gl`) and move to `app/Ledger/balances.py`; backfill command; reconciliation command R1–R10; manual journals with maker-checker; trial balance and GL detail screens; one-month shadow run; switch-over. |

**Acceptance criteria**
1. Inserting an unbalanced entry, a single-line entry, or a line on a control account without a subledger account fails **at commit** (tests bypass the service layer). UPDATE or DELETE on journal tables fails. Posting into a `closed` period fails.
2. Posting the same source event twice creates one journal (idempotency).
3. Backfill on the demo DB and on test fixtures: **R1–R10 report zero differences**, including reversed deposits, mid-month rate changes, approved-unpaid and paid periods.
4. The full existing suite passes in `legacy`, `shadow` and `gl` modes.
5. In `gl` mode, `compute_payouts` for every historical approved period reproduces the stored payouts exactly.
6. Approving an interest period posts one entry dated `period_end` with one Dr/Cr pair per payout. Marking a payout paid posts Dr 2110 / Cr bank. **Investor funds (2100) are untouched by interest.**
7. A manual journal by user A can't be approved by A, and can't post to a GL account with `allow_manual_posting = false`.
8. Trial balance per branch and overall balances. Every control account equals Σ its subledger.
9. One full month-end in shadow mode with the nightly reconciliation reporting zero differences, before switch-over (operational criterion, signed off by finance).

## Phase 5 — Loan products and origination

| | |
|---|---|
| **Goal** | Configurable products. Applications from intake through credit analysis, approval, offer, conditions and disbursement. |
| **Dependencies** | 3 (applications, screening), 4 (posting). Q-C2 (product catalogue), Q-C4, Q-C5 (templates), Q-C6 (fee treatment), Q-C10 (related-party limit), Q-F10 (IFRS 9 fees), Q-M8 (approval limits). |
| **Main tables** | `products`, `product_versions`, `fee_definitions`, `product_gl_mappings`, `classification_sets`, `classification_buckets`, `party_pricing_overrides`, `employers`; extend `loan_applications`; `credit_assessments`, `credit_decisions`, `offers`, `pre_disbursement_conditions`, `disbursement_requests`, `loans`, `loan_guarantors`, `loan_schedules`, `loan_schedule_lines`, `accounts` (collection, loan), `loan_collateral` (link only), `commissions`. |
| **Work** | Product editor with version publish (maker-checker) and parameter validation; schedule generator (flat, reducing; amortising, interest-only bullet, full bullet; frequencies); application workflow and multi-level approval by amount; offer letter generation; disbursement with fee treatments and postings (03 §4.2); IPF first-instalment condition; commissions accrual. Migration rehearsal 1. |

**Acceptance criteria**
1. Editing a published product version is impossible. A new version doesn't change any existing loan's schedule or fees.
2. Schedule generator matches hand-calculated schedules to the cent for: flat monthly, reducing monthly, interest-only + bullet, full bullet (with daily accrual), several day counts. Last instalment absorbs rounding. Totals reconcile.
3. A loan above the approver's limit requires the next approval level. The application maker can't approve. Committee approvals need the configured number of distinct members.
4. Disbursement posts exactly the documented lines for each fee treatment (deduct, capitalise, bill separately; income vs pass-through). MCA nets to the payout amount. TB balances.
5. Related-party limit: booking an Nth loan in a related group above the configured limit is refused with the reason.
6. A Not qualified screening outcome without an approved override blocks credit analysis (from phase 3, still enforced).
7. Migration rehearsal: sample of the legacy lending book (or a synthetic file in the agreed format) loads into products, loans and schedules, with a reconciliation report.

## Phase 6 — Interest, penalties, classification (with the EOD framework)

| | |
|---|---|
| **Goal** | Daily accrual, penalties, suspense, classification, in-duplum checks, schedule recalculation. All run by idempotent EOD. |
| **Dependencies** | 5. Q-C3 (classification buckets), Q-F2 (day count), Q-F5 (suspense on transition), Q-CO4 (in duplum), Q-F11 (EOD blocking). |
| **Main tables** | `business_days`, `batch_runs`, `batch_steps`, `accrual_runs`, `loan_classification_history`, `loan_charges` (recurring fees), `account_balance_snapshots` (EOD). |
| **Work** | EOD framework (moved from phase 12); accrual (performing → income, NPL → suspense); penalty DD+grace per product; classification transitions with suspense transfer; recurring fees; rate change and tenor change → new schedule version (keep end date / extend term); interest stop/waiver via change requests; in-duplum flagging. |

**Acceptance criteria**
1. Running EOD twice for the same business date posts nothing the second time. Killing it mid-step and resuming completes with the same totals as an uninterrupted run.
2. With the scheduler down for 3 days, catch-up runs D, D+1, D+2 in order. D+1 can't start before D is done.
3. Accrual for a fixture portfolio over a month equals the hand-calculated total to the cent, per loan and in total, for each day-count convention.
4. A loan crossing the NPL threshold on day 91 (or per product) moves to suspense accrual. Accrued-unpaid interest transfers per policy. Classification history is recorded. Check-off products with penalty disabled are never penalised.
5. Rate change with "keep maturity" produces a new schedule version with a changed instalment. "Extend term" keeps the instalment and adds periods. The old version remains readable.
6. A loan with `interest_stopped` accrues nothing. Stopping requires an approved change request.
7. EOD verifies Σdr = Σcr per branch and snapshot = line aggregate for touched accounts, and fails loudly otherwise.

## Phase 7 — Repayments, M-Pesa and notifications

| | |
|---|---|
| **Goal** | Every incoming payment captured, matched, allocated by waterfall and posted. Reminders by SMS and email. |
| **Dependencies** | 6. M-Pesa Daraja credentials and paybill (Q-IT11), SMS provider (Q-IT7), Q-C7 (prepayment effect). |
| **Main tables** | `inbound_payments`, `repayment_allocations`, `pdc_register`, `notifications` (outbox with channel), `notification_templates`, `employers` (check-off remittances). |
| **Work** | M-Pesa C2B validation and confirmation endpoints (signature/IP allow-list, idempotent by receipt no.); bank transfer and cheque capture; check-off bulk remittance import and auto-reconcile; suspense handling; MCA sweep in EOD; waterfalls (repayment vs disposal); early settlement quotes; reversals (bounced cheques, M-Pesa reversals); SMS adapter; reminder schedule (7 days before, due date, arrears). |

**Acceptance criteria**
1. The same M-Pesa confirmation delivered twice creates one `inbound_payment` and one journal. An unknown bill reference lands in suspense (2210) and can be matched later by a different user.
2. Allocation follows the product waterfall exactly, for hand-built cases incl. partial payments, overpayment left on the MCA, and NPL suspense recognition.
3. Collateral disposal proceeds follow the disposal waterfall.
4. Bounced cheque reversal restores the schedule's due amounts and reverses the journals exactly.
5. Settlement quote = sum of outstanding components (+ configured early-settlement charge) and, if paid on that date, closes the loan with zero balance.
6. A check-off remittance file with 100 rows auto-matches by employee/loan number. Exceptions are listed. Totals reconcile to the bank receipt.
7. Reminder SMS are queued, never sent synchronously. Templates use configured rates (no literal "5%"). Opt-out is respected for marketing but not for statutory notices (per Q-CO7).

## Phase 8 — Collateral, insurance, restructuring, recoveries, provisioning, write-off

| | |
|---|---|
| **Goal** | Secure, monitor and recover the book. |
| **Dependencies** | 7. Q-F3 (provisioning method and rates), Q-CO7 (notice wording). |
| **Main tables** | `collateral_items`, `loan_collateral` (full), `valuations`, `insurance_policies`, `insurance_claims`, `loan_restructures`, `collection_notes`, `collection_arrangements`, `notices`, `provision_runs`, `provision_lines`, `write_offs`. |
| **Work** | Collateral register (types, shared collateral, LTV, revaluation diary, unsecured flag on expiry); insurance renewals and premium recovery; restructure / reschedule / top-up / refinance with max count and fee; litigation flag; recoveries diary, arrangements, notices; provisioning run (EOM); write-off and post-write-off recoveries; loan closure workflow (FSD checklist). Migration rehearsal 3. |

**Acceptance criteria**
1. One collateral item pledged to two loans: LTV per loan and per group is correct. Releasing collateral while the outstanding balance requires it is refused.
2. Expired insurance or valuation flags the facility unsecured on the next EOD and appears on the dashboard.
3. A 4th restructure (with max 3) is refused. A restructure creates a new schedule version and charges the configured fee.
4. Provision run posts only the movement versus the previous run. Re-running for the same date is idempotent.
5. Write-off (maker-checker, approval policy by amount) posts the documented lines and leaves interest/penalty suspense at zero for that loan. A later recovery posts to recoveries income.
6. Closure workflow can't complete while any checklist item is open (stop recurring fees, release securities, cancel insurance, clearance letter generated).

## Phase 9 — Trade finance, finance and treasury

| | |
|---|---|
| **Goal** | Guarantees with cash margins. Finance back office (bank reconciliation, fixed assets, prepayments, borrowings, T-bills/bonds). |
| **Dependencies** | 4, 7. Q-F8 (TF accounting), Q-CO6 (AML system). |
| **Main tables** | `tf_products`, `tf_guarantees`, `accounts` (tf_margin), `bank_statement_lines`, `bank_reconciliations`, `fixed_assets`, `depreciation_runs`, `prepayments`, `borrowings`, `securities_holdings`. |
| **Work** | TF request → AML hold → approval (return-for-edit supported) → issue → expiry/refund, with memo postings; bank statement import (CSV/MT940 if available) and matching; fixed asset register and monthly depreciation; prepayment amortisation; borrowings with interest accrual and WHT; T-bill and bond holdings and accruals. |

**Acceptance criteria**
1. A TF guarantee for a beneficiary on a watchlist stops at `aml_hold` and needs AML-officer approval. Limit and balance validation refuses guarantees exceeding the available margin.
2. Issue and expiry post and reverse the memo contingent entries. Margin refund leaves the client's margin account at zero.
3. Bank reconciliation: imported statement lines auto-match to journal lines by amount, date and reference. The reconciliation report balances to the statement closing balance.
4. Depreciation for a fixture register matches hand calculation. Re-running a month is idempotent.
5. Borrowing interest accrual and payment post the documented lines including WHT.

## Phase 10 — Integrations

| | |
|---|---|
| **Goal** | External connections hardened and signed off. |
| **Dependencies** | 7, 8. Q-CO5 (CRB), Q-IT7, Q-IT11. |
| **Main tables** | `integration_endpoints`, `integration_messages` (request/response log, redacted), `crb_submissions`. |
| **Work** | CRB data submission and enquiries (with consent purpose `credit_bureau_check`); M-Pesa hardening (reconciliation against the M-Pesa statement, B2C for disbursements if adopted); SMS delivery reports; integration test suite per FSD p.76 (endpoints, no test data in prod, data feeds, access); API monitoring. |

**Acceptance criteria**
1. CRB submission file or API payload for a fixture portfolio matches the bureau's specification validator. Enquiries require recorded consent.
2. Daily M-Pesa reconciliation flags any C2B receipt in the M-Pesa statement not present in `inbound_payments`, and vice versa.
3. Integration messages are logged with secrets and personal fields redacted.
4. A test-mode flag guarantees sandbox endpoints in non-production (test asserts config).

## Phase 11 — Reports, risk and audit

| | |
|---|---|
| **Goal** | Statutory, management and credit reports. AML monitoring, case management and audit tooling. |
| **Dependencies** | 4–10. Q-F7 (budgets), Q-IT6 (BI). |
| **Main tables** | `report_schedules` (generalised), `budgets`, `aml_rules`, `aml_alerts`, `cases`, `case_events`. |
| **Work** | Trial balance, BS, P&L (company, branch, segment); credit reports (portfolio, PAR, NPL, arrears, rescheduled, stopped interest, expected repayments, exposure by dimensions); IR reports (placement register, WHT register); finance reports (commission payments); scheduled delivery via the outbox; AML transaction monitoring rules and alert case management; data-access and out-of-portfolio reports; audit exports. |

**Acceptance criteria**
1. TB, BS and P&L for a fixture period match hand-built expected statements, by branch and consolidated. BS balances.
2. PAR buckets and NPL report match the classification history for the fixture portfolio.
3. Every report export is audited and permission-gated (`report.export.<name>`), as today.
4. An AML rule (e.g. cash deposits above a threshold within N days) raises an alert, opens a case, and appears on the risk dashboard. Closing a case requires a resolution note.
5. Out-of-portfolio access by a relationship officer appears on the risk report the next day.

## Phase 12 — Hardening and EOM/EOY

| | |
|---|---|
| **Goal** | Production-grade operations: period close automation, performance, security, backup and restore, DR. |
| **Dependencies** | 2–11. Q-IT1, Q-IT3. |
| **Main tables** | `gl_periods` close workflow, `ops_checklists`. |
| **Work** | EOM (provisions, depreciation, accruals, interest approval gate, reconciliations, soft close → close) and EOY (P&L roll); load tests (target volumes from Q-IT12); security review (OWASP ASVS L2 checklist), dependency audit, secrets in a vault; idle timeout, password history, optional single session; restore drill of DB + document store; monitoring and alerting; read-only reporting replica. |

**Acceptance criteria**
1. EOM can't close while the month's investor interest is unapproved, bank reconciliation is incomplete (override with approval), or blocking cases are open. EOY close posts the P&L roll and opens new periods.
2. Load test: EOD for the target loan volume completes within the agreed window. API p95 latency under target with N concurrent users.
3. **Restore drill:** the database and documents restored into a clean environment from backups. Reconciliation R-checks and document hash checks pass. Documented RTO/RPO met.
4. No high or critical findings open from the security review and dependency audit.

## Phase 13 — Migration and UAT

| | |
|---|---|
| **Goal** | Final data migration of the lending book (and any remaining customers), parallel run, user acceptance and go-live. |
| **Dependencies** | All. Rehearsals from phases 5–8. Q-IT8 (source system and extract format). |
| **Main tables** | `migration_batches`, `migration_exceptions`. |
| **Work** | Final extract → transform → load; migration audit (FSD p.77: counts, balances, GL, schedules, product mapping); parallel run for one month-end; UAT scripts per department; training; cutover runbook and rollback plan. |

**Acceptance criteria**
1. Migration audit: customer and account counts match. Outstanding principal, interest receivable/suspense and fees per loan match the source to the cent. GL balances per account and branch match the source TB at cutoff.
2. Regenerated schedules for migrated loans match the source's remaining instalments within an agreed tolerance (expected 0). Exceptions are listed and signed off.
3. Duplicate detection on migrated parties: no unresolved identifier collisions.
4. UAT sign-off by credit, finance, risk, investor relations and IT for their scripts.
5. Cutover rehearsed end to end at least twice, with timing recorded.

---

## Go-live waves (recommended)

| Wave | Contents | Can go live after |
|---|---|---|
| **A** | Investments on the GL, parties/KYC, documents, maker-checker, RBAC, AI pre-selection used by credit alongside the existing lending process | Phases 2a, 2b, 3, 4 + the phase 12 items that apply (restore drill, security review) + DPIA sign-off |
| **B** | Lending origination and servicing | Phases 5–8 + phase 12 + phase 13 lending migration |
| **C** | Trade finance, treasury, full reporting, AML monitoring, CRB | Phases 9–11 (can follow B by weeks without blocking lending) |
