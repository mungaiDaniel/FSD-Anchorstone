# 07 — Open questions

These are the decisions that couldn't be made from the FSD or the code.

- **Grouped by who must answer:** management, credit, finance, compliance, IT.
- **Every question has a recommended default.** If it isn't answered by the phase listed, we build the default and record it, as `CLAUDE.md` asks ("ask, propose a default").
- **IDs match the references** in documents 01–06.

---

## Management

| ID | Question | Why it matters | Recommended default | Needed by |
|---|---|---|---|---|
| **Q-M1** | Does the investment side stay as **one open-ended running balance per investor with one flat rate and monthly payout**, or move to the FSD's **term placements** (receipts with tenors, maturity, rollover instructions, rate by tenor)? Is there any savings product (the FSD's "Savings Report")? | Determines whether we build `placement_receipts`, daily accrual and maturity processing, and how investor statements look. It's the biggest scope swing on the funding side. | **Keep today's model.** Design the GL and accounts so term placements can be added later as a new product kind. No savings product. | Phase 4 (GL posting rules) |
| **Q-M2** | Numbering formats: party number, loan account number (FSD: 11 digits = branch + product + sequence), collection account number. Confirm that `ACL-` investor codes never change. | Printed on letters, statements, M-Pesa bill references. Hard to change once issued. | `ACL-…` unchanged. Party `P-0000001`. Loan `BBBPPPNNNNN` (11 digits). MCA `BBB900NNNNN`. | Phase 2b |
| **Q-M3** | Will investors or borrowers get any self-service channel (portal, app, e-banking), as the FSD objectives imply? | Affects authentication design, statement delivery, "e-banking customer" emails in trade finance. | **No customer portal in phases 2–13** (current decision). Email and SMS only. Revisit after wave B. | Phase 5 |
| **Q-M4** | What are Anchorstone's actual branches (names, codes), today and planned? The FSD gives 3 contradictory lists. | Branch codes are in account numbers and on every journal line. | One branch: `000 Head Office`. Others added as reference data when opened. | Phase 2a |
| **Q-M5** | Should edits to existing investors (name, email, ID, payout details) and creation of new investors become **maker-checker**, as the FSD requires for all static data? This changes today's behaviour, where staff edit immediately. | Control vs speed for investor relations. | **Yes** for identity and payout fields (ID, KRA PIN, name, payout account, statement email). **No** for phone, address and notes. New investors are created immediately but are "KYC pending" until a second person verifies. | Phase 2b |
| **Q-M6** | Is more than one legal entity needed (e.g. a separate lending company and investment company) with separate books? | Multi-entity GL changes the chart, inter-company postings and reports. | **Single entity.** Entity is not modelled. | Phase 4 |
| **Q-M7** | Which existing investors are companies, chamas, SACCOs or other organisations rather than individuals? | The party migration needs the right party type and KYC fields. | All migrated as persons. Investor relations reviews a generated list and reclassifies before the migration runs. | Phase 2b |
| **Q-M8** | Approval limits: who may approve what amount (loans, disbursements, withdrawals, write-offs, manual journals), and committee composition and quorum? | Feeds `transaction_limits` and `approval_policies`. | Withdrawals: any admin ≤ KES 1,000,000, finance manager above. Loans: credit officer ≤ 500,000, credit manager ≤ 2,000,000, committee (2 of 3) above. Write-offs: committee always. Manual journals: finance manager. *Placeholders to be replaced.* | Phase 2a (framework), phase 5 (values) |

## Credit

| ID | Question | Why it matters | Recommended default | Needed by |
|---|---|---|---|---|
| **Q-C1** | Which KYC fields are **mandatory** for individuals and for companies? (The FSD says "fields in bold are mandatory", but the bold didn't survive.) | Validation, KYC completeness status, migration exceptions. | Individuals: name, ID/passport, KRA PIN, DOB, mobile, physical address, next of kin. Companies: legal name, reg no., KRA PIN, registration date, ≥ 1 director with ID, mobile, physical address. | Phase 2b |
| **Q-C2** | What is Anchorstone's product catalogue? Names, kinds, rates, fees, tenors, frequencies, penalty settings. (FSD product names are another lender's.) | Product engine configuration. Screening rules per product. | Start with 3 configurable products: (1) amortising business loan, (2) short bullet working-capital loan, (3) check-off loan. Values from management. | Phase 5 |
| **Q-C3** | Classification buckets (days past due for Normal / Watch / Substandard / Doubtful / Loss) per product, and when interest moves to suspense (90 days, or immediately as the FSD says for IPF). | Accrual vs suspense, provisioning, reports. | Normal 0–30, Watch 31–90, Substandard 91–180, Doubtful 181–360, Loss > 360. Suspense from day 91. IPF the same unless decided otherwise. | Phase 6 |
| **Q-C4** | Fixed vs variable rates: if variable, what's the base (CBK rate, internal base rate) and repricing frequency? | Rate model and schedule recalculation. | **Fixed only at launch.** Variable modelled (rate type + base) but disabled. | Phase 5 |
| **Q-C5** | Offer letter, fee schedule, demand notice, proclamation, sale notice and clearance letter templates (the FSD says "as per templates shared"). | Document generation. | Plain branded templates drafted by us, approved by legal before use. | Phase 5 / phase 8 |
| **Q-C6** | For each fee: deducted at disbursement, capitalised into principal, or billed separately? Income or pass-through (tracking provider, risk fund, insurance)? One-off or monthly? (FSD C-5, C-11.) | Postings and customer statements. | LAF, membership, CRB, legal and search: deducted, income. Tracking: monthly, billed, pass-through. Risk fund: deducted, pass-through. Insurance premium: deducted, pass-through. | Phase 5 |
| **Q-C7** | On a lump-sum prepayment: shorten the term, or reduce the instalment? Any early-settlement charge? | Schedule recalculation and settlement quotes. | Reduce the instalment, keep maturity. Early settlement: one month's interest (configurable per product). | Phase 7 |
| **Q-C8** | On the AI review screen, may reviewers "confirm all remaining" high-confidence fields that passed every check, or must each field be clicked? | Review throughput vs assurance. | **Allowed** for fields ≥ the per-type confidence threshold with no failed validator or cross-check. Never for ID numbers, KRA PINs or amounts. | Phase 3 |
| **Q-C9** | FSD special condition "suspend interest for performing accounts but still charge on client's account": what does it mean? | Accrual logic. | Interpreted as: stop recognising income (suspense) while still accruing the amount owed by the client. Implemented as a manual move to suspense with approval. | Phase 6 |
| **Q-C10** | The related-party limit "maximum loan accounts allowable are 3": per borrower, or per related-party group? Active loans only? | Origination rule. | Per related-party group, active loans only, configurable (default 3). | Phase 5 |
| **Q-C11** | What extraction accuracy is acceptable per document type before AI goes live (e.g. ≥ 99% exact match on ID numbers, ≥ 97% on statement amounts after review flags)? Who signs off? | The evaluation harness gate for any model or prompt change. | ID/KRA/registration numbers ≥ 99%. Names ≥ 97%. Statement amounts ≥ 98% with balance-arithmetic flags catching the rest. Signed off by the credit manager. | Phase 3 |

## Finance

| ID | Question | Why it matters | Recommended default | Needed by |
|---|---|---|---|---|
| **Q-F1** | The chart of accounts (the FSD says it "will be shared separately"). | GL seed, posting rules, reports. | Use the skeleton in 03 §2. Finance renames and extends it before phase 4 go-live. | Phase 4 |
| **Q-F2** | Day count for **loans**: actual/365 fixed (as investor interest uses today), or actual/actual "considering leap years"? Per product? | Interest amounts in leap years. | ACT/365F everywhere (consistent with investor interest). ACT/ACT available per product. | Phase 5 |
| **Q-F3** | Provisioning: regulatory bucket rates, or IFRS 9 expected credit loss (staging, PD/LGD)? Rates per class? | Provision runs and expense. | Bucket rates at launch (Normal 1%, Watch 3%, Substandard 20%, Doubtful 50%, Loss 100%) as a *management overlay*. An IFRS 9 ECL model is a later project with the auditors. | Phase 8 |
| **Q-F4** | Which Anchorstone bank account (and M-Pesa paybill) received historical investor deposits, and which pays withdrawals and interest? How should future receipts map? | Backfill (03 §7.2) and bank reconciliation. | History by method: bank transfer → main account, M-Pesa → paybill float, cheque → clearing, cash → cash on hand. Going forward staff pick the receiving account on each deposit. | Phase 4 |
| **Q-F5** | Accrual policies: (a) post an estimated investor-interest accrual at month end before approval? (b) on loan NPL transition, move accrued-but-unpaid interest from income to suspense? (c) on return to performing, reverse it back? (d) allow "late corrections" dated today for closed periods? | GL posting rules and the P&L timing. | (a) No: post at approval dated period end, and close the month only after approval. (b) Yes. (c) Yes, for amounts still unpaid. (d) Yes, finance-approved, with a reason. | Phases 4 and 6 |
| **Q-F6** | Withholding tax on agent and staff commissions: rate and treatment? | Commission postings. | Agents 10%, staff via payroll (excluded from this system). *Confirm with tax adviser.* | Phase 5 |
| **Q-F7** | Budgets: who enters them, at what granularity (GL account × branch × month)? | Budget vs actual reports. | Annual budget per GL account per branch per month, imported from Excel by finance. | Phase 11 |
| **Q-F8** | Trade finance accounting: confirm the reading of the FSD's guarantee income and margin refund entries (03 §4.6), and whether guarantees go off balance sheet as memo entries. | TF postings. | As proposed in 03 §4.6, memo accounts for contingent liabilities. | Phase 9 |
| **Q-F9** | Will finance keep an external accounting package for statutory accounts (exporting the TB and journals), or report fully from this system? | Export formats and close process. | Report from this system. Provide CSV/Excel TB and journal exports for auditors. | Phase 11 |
| **Q-F10** | IFRS 9: should loan fees that are integral to the loan (e.g. LAF) be deferred and amortised over the effective interest rate, rather than recognised as income at disbursement (the FSD's approach)? | Fee income timing. A potential audit finding. | Follow the auditors. Until told otherwise, recognise at disbursement as the FSD shows, but tag fees `integral = true` so EIR amortisation can be switched on without migration. | Phase 5 |
| **Q-F11** | Should open exceptions block **EOD** (FSD) or only **EOM close**? | Operational risk: blocking EOD stops interest accrual. | Block **EOM** only. EOD always runs and reports exceptions. | Phase 6 |

## Compliance

| ID | Question | Why it matters | Recommended default | Needed by |
|---|---|---|---|---|
| **Q-CO1** | Lawful basis per purpose under the Kenya DPA (KYC under AML law vs consent for AI processing and marketing). Treatment of guarantors, directors and next of kin. What happens to confirmed data after AI consent is withdrawn? Also applies to **existing investor data** already held. | Consent design, notices, retention, data-subject rights. | KYC: legal obligation. AI processing: consent (manual path available). Marketing: consent. Confirmed data stays under the KYC basis after AI consent is withdrawn. | Phase 2b |
| **Q-CO2** | Where may personal data and documents be stored and processed (Kenya only? Azure South Africa? EU?), and which safeguards are needed for transfers, including the Claude API? | Hosting region, storage provider, AI go-live. | Database and documents in the closest acceptable region per compliance. Claude API under a processor agreement with documented transfer safeguards. Go-live gated on the assessment. | Phase 2a (storage), phase 3 (AI) |
| **Q-CO3** | Access-control policy details: should relationship officers be **blocked** from customers outside their portfolio, or only **flagged** (FSD says flag)? Watermark downloaded KYC documents? | RBAC scoping, data-access reports. | Flag (log + report), don't block, except for staff accounts and PEPs (blocked without a specific permission). Watermark KYC downloads. | Phase 2a |
| **Q-CO4** | Does the in duplum rule (Banking Act s.44A) bind Anchorstone as a non-bank lender, or should it be applied as policy? | Whether interest and penalties stop at the principal amount on NPLs. | Apply as a **policy control**: flag and stop accrual when interest + charges reach outstanding principal on non-performing loans. | Phase 6 |
| **Q-CO5** | CRB obligations: which bureaus, submission frequency and format, and the consent wording for enquiries. | Phase 10 integration. Negative-information notices. | Monthly submissions to one licensed bureau via its API or file format. Consent captured at application. | Phase 10 |
| **Q-CO6** | Is there an existing AML system or screening list provider (the FSD mentions integrating "the company Anti Money Laundering System")? Which lists (UN, OFAC, local PEP)? | Build vs integrate for screening. | No external system. Internal blacklist + UN Security Council list import + manual PEP flag at launch. Commercial list provider evaluated in phase 11. | Phase 2b |
| **Q-CO7** | Legal review of recovery notices and SMS wording (the FSD's repossession SMS threatens disposal "without any further reference"), and of which notices customers can opt out of. | Consumer protection and legal risk. | All recovery templates approved by legal before use. Statutory and contractual notices can't be opted out of. Marketing can. | Phase 7 |
| **Q-CO8** | Retention periods per record type (KYC, documents of approved and declined applicants, AI outputs, statement transactions, screening runs, audit logs). | Retention jobs and DPA compliance. | As 05 §9.3 and 04 §2.5: 7 years after relationship end for KYC and transactions, 24 months for declined applications and raw AI outputs, 7 years for screening runs and audit logs. | Phase 3 |
| **Q-CO9** | Are ID photos (faces) biometric data under the DPA in our use? May we store them? May we send them to the AI service? | Document handling and AI minimisation. | Store ID images (needed for KYC). **Don't** extract or template faces. Send only the text-bearing ID images to the AI. | Phase 3 |
| **Q-CO10** | May **age** be used in pre-selection rules (e.g. minimum 18, or maximum age at maturity for long tenors)? Any other attributes forbidden beyond the obvious protected ones? | Rule registry's protected-attribute list. | Allowed only for legal capacity (≥ 18) and maximum age at maturity with a documented justification. Gender, marital status, religion, ethnicity and health are blocked. | Phase 3 |
| — | **Also from compliance** (05 §9.6): DPIA for AI processing, ODPC registration status, updated privacy notice to clients, breach notification procedure, data-subject rights procedure. | Go-live gates for wave A. | We provide the data-flow descriptions and tooling. Compliance owns the documents. | Before wave A go-live |

## IT

| ID | Question | Why it matters | Recommended default | Needed by |
|---|---|---|---|---|
| **Q-IT1** | Hosting: cloud provider and region, or on-premises? Required availability, RTO/RPO, disaster recovery site (FSD wishlist)? | Storage backend, worker deployment, backups, DR tests. | A managed PostgreSQL + container hosting in the region approved under Q-CO2. Azure Blob for documents. Point-in-time DB recovery. RPO 15 min, RTO 4 h. | Phase 2a |
| **Q-IT2** | May user accounts be hard-deleted (today `DELETE /users/<id>` exists), or disable only? | Audit integrity (FSD: logs must not be altered). | **Disable only.** Remove the delete endpoint. | Phase 2a |
| **Q-IT3** | Has a backup restore ever been tested? Who owns restore drills? Is the OneDrive backup (currently off) the intended long-term solution? | Recoverability of the live investor book. | Turn on managed point-in-time backups and keep the OneDrive dump as an off-site copy. Quarterly restore drill owned by IT. First drill in phase 2a. | Phase 2a |
| **Q-IT4** | "Print passbook" (FSD transaction posting): is a passbook needed? | Printing support. | No passbook. PDF statements on demand (exists). | Phase 11 |
| **Q-IT5** | Password and session policy: monthly expiry (FSD) vs no forced expiry (current, and NIST guidance)? Single concurrent session? Idle timeout? "Restricted copy/paste"? | Admin module changes. | 10+ characters (current), history of 5, no forced expiry, 30-minute idle timeout, single session optional per role, drop copy/paste restriction. | Phase 12 |
| **Q-IT6** | Is a BI tool (Power BI, Metabase) acceptable for ad-hoc reports instead of a built-in report designer? | Avoids building a report designer. | Yes: a read-only reporting replica + Metabase or Power BI for ad hoc. Built-in reports for statutory and operational needs. | Phase 11 |
| **Q-IT7** | SMS provider (e.g. Africa's Talking or a Safaricom bulk SMS reseller), sender ID, budget. | Phase 7 adapter. | Africa's Talking (simple API, Kenyan sender IDs), behind our own adapter so the provider can be switched. | Phase 7 |
| **Q-IT8** | Where is the current lending book held (the FSD assumes an "old core banking system")? What extract formats are available, and who owns the extract? | Migration rehearsals from phase 5. | Ask for a full CSV/Excel extract of customers, loans, schedules, payments and the GL TB at a cutoff date. We define the template in phase 5. | Phase 5 |
| **Q-IT9** | Should staff be able to upload Office documents (Word/Excel), or PDF and images only? | Document store conversion and virus-scan scope. | PDF and images only. Staff export Office files to PDF before upload. | Phase 2a |
| **Q-IT10** | Should the **system administrator** role lose business approval permissions (segregation of duties), so IT can't approve withdrawals or interest? | Today `super_admin` can do everything `admin` can. | **Yes.** System administrators manage users and settings only. Business approvals need business roles. | Phase 2a |
| **Q-IT11** | M-Pesa: paybill number(s), Daraja API credentials and environment, who registers the callback URLs, and whether B2C disbursements are wanted. | Phase 7 integration. | C2B on the existing paybill via Daraja. Disbursements by bank transfer at launch (no B2C). | Phase 7 |
| **Q-IT12** | Expected volumes (customers, active loans, daily transactions, documents per month, concurrent staff) for the next 3 years. | Load-test targets, EOD window, AI budget. | Plan for 20,000 parties, 10,000 active loans, 2,000 receipts/day, 3,000 documents/month, 50 concurrent staff. | Phase 12 (targets), phase 3 (AI budget) |

---

## Top 10 (most decision-critical)

1. **Q-M1:** keep the running-balance investment model, or move to term placements?
2. **Q-C2:** Anchorstone's product catalogue and parameters.
3. **Q-CO2 / Q-IT1:** where data and documents may live (hosting region, cross-border transfer to the Claude API).
4. **Q-CO1 + DPIA (05 §9.6):** lawful basis, consent and DPIA for AI processing. A go-live gate.
5. **Q-F1:** the chart of accounts.
6. **Q-M8:** approval limits and committee rules.
7. **Q-C3 / Q-F3:** classification buckets, suspense trigger and provisioning method.
8. **Q-M5:** maker-checker on investor and party edits (changes current behaviour).
9. **Q-IT8:** source and format of the existing lending book for migration.
10. **Q-C6 / Q-F10:** fee treatment (deduct / capitalise / pass-through) and IFRS 9 fee recognition.
