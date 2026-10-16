# 04 — Cross-cutting designs

This document covers four designs that every later module depends on:
1. maker-checker;
2. document storage;
3. background jobs;
4. roles and permissions.

---

## 1. Generic maker-checker framework

### ADR-04-1 — One change-request framework, with domain approvals kept where they already work

**Context**

Today maker-checker exists in **two hand-written places**:

| Where | Maker | Checker |
|---|---|---|
| Withdrawals | `requested_by` | `decided_by` (must differ, `Forbidden("Maker-checker: …")`) |
| Interest periods | `calculated_by` | `approved_by` (must differ) |

The FSD wants maker-checker on far more:
- every static-data capture or amendment;
- custom interest rates and repayment-date changes;
- restructures, write-offs and journal postings;
- account approvals and pricing overrides;
- AI field confirmations;
- screening-rule publication;
- departmental and multi-level approvals by amount.

Writing a bespoke status machine per feature would repeat the same bugs.

**Options considered**

| Option | Assessment |
|---|---|
| A. Each module adds `pending/approved` columns and its own checks (today's pattern) | Fine for records that *are* requests (a withdrawal is a request by nature). For edits to existing records ("change this borrower's KRA PIN") the record would need shadow columns for proposed values. Inconsistent rules, and no single approvals inbox. |
| B. **Generic `change_requests`**: a proposed action plus a payload, applied by a registered handler when approved. Records that are inherently requests (withdrawals, interest periods, disbursements, write-offs) may keep their own status but **must use the same policy and decision functions** | One inbox, one rule set, one audit pattern. Domain records stay readable. |
| C. Full workflow engine (BPMN, e.g. Camunda) | Powerful, but heavy to operate and overkill for approve/reject/return with amount thresholds. |

**Decision.** **Option B.**

**Consequences**
- **Existing withdrawals and interest periods keep their tables and endpoints.** Their checks move into `app/Approvals/policy.py` (`assert_can_decide(request, actor)`), so the maker ≠ checker rule is implemented once.
- **Static-data edits stop applying immediately** wherever a policy requires approval. Staff see "Submitted for approval" instead. This is a visible behaviour change for investor edits (Q-M5).

### 1.1 Tables

| Table | Key fields |
|---|---|
| `change_requests` | `id`, `request_type` (e.g. `party.update_identity`, `loan.change_rate`, `loan.write_off`, `gl.manual_journal`, `screening.publish_ruleset`, `product.publish_version`), `entity_type`, `entity_id` (nullable for creations), `payload` (jsonb: proposed values or command arguments), `base_version` (the target row's `date_updated`, or a hash of the fields being changed), `amount`, `currency` (for policy thresholds), `branch_id`, `status` (`draft` / `pending` / `returned` / `approved` / `applied` / `rejected` / `cancelled` / `expired` / `failed`), `maker_user_id`, `submitted_at`, `reason`, `expires_at`, `applied_at`, `result` (jsonb), `policy_id`, `levels_required`, `levels_done` |
| `change_request_events` | `id`, `request_id`, `actor_user_id`, `action` (`submit` / `approve` / `reject` / `return` / `resubmit` / `cancel` / `apply` / `expire`), `level`, `comment`, `at` |
| `approval_policies` | `id`, `request_type`, `min_amount`, `max_amount`, `levels` (jsonb: e.g. `[{"permission":"loan.approve.l1"},{"permission":"loan.approve.committee","count":2}]`), `same_branch_required`, `expiry_hours`, `active` |

**Database guarantees**
- A trigger on `change_request_events` refuses `approve` / `reject` / `return` where `actor_user_id = maker_user_id`.
- A unique `(request_id, actor_user_id, action='approve')` stops the same person approving at two levels.
- The same trigger guards the domain tables that keep their own columns: `CHECK (decided_by <> requested_by)` on `withdrawals`, compared case-insensitively on email today and on user id once the IDs are stored.

### 1.2 Lifecycle

```
draft ──submit──▶ pending ──approve (all levels)──▶ approved ──apply──▶ applied
                   │  ▲                                          │
                   │  └──resubmit── returned ◀──return──┘        └─(handler error)─▶ failed
                   ├──reject──▶ rejected
                   ├──cancel (maker)──▶ cancelled
                   └──(expires_at)──▶ expired
```

### 1.3 Rules

| Rule | Detail |
|---|---|
| Maker ≠ checker | At every level, **and no person approves twice** across levels. |
| Policy routing | The policy is chosen at submit time by `request_type` and `amount`. The approver needs the level's permission **and** a transaction limit (§4.4) ≥ the amount. |
| Re-validation at approval | The handler's `validate()` runs again on approval, under the same locks the direct action would take (e.g. `lock_account`). |
| Stale requests | If `base_version` no longer matches the target, the request fails with "The record changed after this request was made. Submit a new request." Nobody approves a change against data they never saw. |
| Applying | The final approval applies the change **in the same transaction**, with the audit entry. On success the request moves straight to `applied`. Handlers are plain Python functions registered in a dictionary: `{"party.update_identity": PartyIdentityHandler}`, each with `validate(payload)`, `apply(payload, actor)` and `describe(payload)` (for the inbox and diff view). |
| Returned for correction | The FSD needs "return to data entry for modification" (trade finance). The maker edits the payload and resubmits. History is kept in events. |
| Expiry | Default 7 days, per policy. An EOD job expires stale requests. |
| Audit | Every event writes `create_audit_log` in the same transaction (`CHANGE_REQUEST_SUBMITTED` / `_APPROVED` / `_APPLIED` …), with old and new values from the handler. |
| UI | An **Approvals inbox** lists requests the user may decide (permission + limit + branch scope + not the maker), with a field-level diff. |
| Tests per handler | Allowed path, maker-is-checker refused, insufficient limit refused, stale base refused, returned-and-resubmitted, expiry. |

### 1.4 What uses which mechanism

| Action | Mechanism |
|---|---|
| Withdrawal, interest period, disbursement request, write-off, provision run, trade-finance guarantee, AI field confirmation (05) | **Domain record with status**, using the shared `assert_can_decide` and approval policies |
| Party identity/KYC edits, investor edits (Q-M5), custom loan rate, repayment-date change, reschedule/restructure, interest stop/waiver, pricing override, product version publish, GL account mapping change, manual journal, screening rule-set publish, branch and reference-data changes, user role and limit changes | **`change_requests`** |
| Recording a deposit, M-Pesa receipt auto-match | **No approval.** Posted immediately, reversible by an admin. Today's rule stays. |

---

## 2. Document storage

### ADR-04-2 — Encrypted object storage behind a `DocumentStore` interface

**Context**
- KYC images, CR12s, title deeds, bank statements and valuation reports are sensitive personal data (Kenya DPA). They are large (multi-page scans, 1–20 MB), and must be linkable to parties, applications, loans and collateral.
- Today only generated PDFs are stored, as `bytea` in `email_attachments` (small, created by the app).

**Options considered**

| Option | Assessment |
|---|---|
| A. PostgreSQL `bytea` (as `email_attachments`) | Simple and transactional. But it bloats the database and backups (the daily `pg_dump` to OneDrive would carry every scan) and makes retention deletion slow. |
| B. Local disk on the API server | Lost on redeploy, can't be shared by several workers, and no encryption by default. |
| C. **Object storage** (Azure Blob Storage / S3 / on-prem MinIO) with app-level envelope encryption; metadata in PostgreSQL | Scales, cheap, private by default, lifecycle rules for retention. |

**Decision.** **Option C.**
- **Interface:** a `DocumentStore` with `put(stream) → key`, `get(key) → stream`, `delete(key)`.
- **Backends:** `local` (dev and tests, under a gitignored folder) and `azure_blob` (production default, because Anchorstone already uses Microsoft 365 / Azure AD for OneDrive backups), or `s3` / MinIO if hosting goes elsewhere.
- **Choice of provider and region** depends on data-residency advice (Q-CO2) and hosting (Q-IT1).

**Consequences**
- Two systems to back up (database plus bucket). Restore drills must cover both.
- Generated statements can stay in PostgreSQL until phase 12.

### 2.1 Encryption at rest

| Layer | Design |
|---|---|
| Per file | A random 256-bit data key per document; content encrypted with **AES-256-GCM** before upload. |
| Key wrapping | The data key is wrapped by a **key-encryption key (KEK)** held in a key vault (Azure Key Vault / AWS KMS), or from `DOCUMENT_KEK` in the environment for single-server deployments. Only `wrapped_data_key` and `encryption_key_id` are stored in `documents`. |
| Storage layer | The provider's own encryption at rest is also on (defence in depth). |
| Key rotation | Re-wrap data keys with the new KEK. File contents don't need re-encrypting. |
| Deletion | **Crypto-shredding:** destroy the wrapped data key, then delete the blob. Backups that still contain the blob become unreadable. This matters for DPA erasure requests. |
| Relation to `SECRET_KEY` | The KEK is **not** derived from `SECRET_KEY` (unlike today's SMTP password encryption in `app/utils/crypto.py`). Rotating the JWT secret must not destroy every document. |

### 2.2 Storage layout and integrity

- **Object key:** `documents/{yyyy}/{mm}/{uuid}`. It contains **no** personal data, names or ID numbers.
- **Integrity:** `sha256` of the *plaintext* is stored and verified on read. Uploading the same file twice for the same party is detected and linked, not stored again.
- **Accepted types:** PDF, JPEG, PNG, HEIC (converted to JPEG on upload), TIFF. Max 25 MB per file (configurable). Office files are converted to PDF or rejected (Q-IT9).
- **Virus scan:** ClamAV on upload, before the file becomes available. A failed scan → `quarantined`, never processed by AI.

### 2.3 Linking

| Mechanism | Detail |
|---|---|
| `document_links` | `(document_id, entity_type, entity_id, purpose)`. One scan can serve a party's KYC **and** an application **and** a collateral record. |
| `documents.document_type` | The *declared* type at upload (national ID, CR12 …). AI classification (05 §4.1) may flag a mismatch, but a person confirms. |
| Versioning | A replacement is a new document linked with `purpose='supersedes:<old_id>'`. Old versions are kept until retention ends (FSD: "store images and signatures that have been amended"). |

### 2.4 Access control and logging

- **No public or pre-signed URLs reach the browser.**
  - Downloads go through `GET /api/v1/documents/<id>/content`.
  - The route checks the permission (`document.view`, plus `document.view.sensitive` for ID and financial documents), then branch and portfolio scope (§4.5).
  - It then streams the decrypted bytes and writes a `data_access_logs` row (`view` / `download`).
- **The frontend keeps today's pattern:** fetch with the auth header, open a blob URL.
- **Watermarking:** an optional "viewed by {user} {time}" watermark on downloaded PDFs of KYC documents (Q-CO3).

### 2.5 Retention

`retention_until` is set from a policy table per document type and party state:

| Document | Retention (proposed default) |
|---|---|
| Customer KYC | 7 years after the relationship ends |
| Declined applications | Shorter (e.g. 2 years) |

Compliance must confirm both (Q-CO8).

- A monthly job lists documents past retention for a records officer to approve deletion (maker-checker).
- A `legal_hold` flag (litigation accounts, FSD) blocks deletion.

---

## 3. Background jobs

### ADR-04-3 — Postgres-backed job queue in a separate worker process; business-date batch runs

**What runs in the background today**

`app/logic/scheduler.py` uses **APScheduler inside the web process**, started on the first request of each process. It runs:
- email queue drain (every 2 minutes);
- monthly AUM report;
- optional daily `pg_dump` backup.

This works because:
- the Dockerfile runs **one** gunicorn worker;
- email drains claim rows with `FOR UPDATE SKIP LOCKED`;
- the AUM job is de-duplicated by `aum_last_month`.

**Problems with that today**
1. **Multiple workers mean multiple schedulers.** The brief says "we run multiple gunicorn workers". Each worker would start its own scheduler:
   - Email is safe (`SKIP LOCKED`).
   - **The daily backup would run once per worker.**
   - Every interval job multiplies.
2. **Long jobs in web processes.** "Send now" runs `drain_queue` inside the HTTP request. EOD runs (thousands of loans) and AI extraction (tens of seconds per document, retries, rate limits) must not live in request threads or web processes that gunicorn may recycle.
3. **Business-date semantics.** Daily accruals must run *once per business date*, even if the server was down that night (catch-up), and be resumable midway.
4. **The FSD's operational requirements:** "initiate, monitor, pause and stop scheduled processes … logs … manual fallback", "automated EOD/EOM/EOY", "restrict end of day until exceptions resolved".

**Options considered**

| Option | Assessment |
|---|---|
| A. Keep APScheduler, but in exactly one dedicated process | Fixes duplication. Still no durable queue, retries, per-task concurrency limits or visibility. AI jobs would need a hand-rolled queue anyway. |
| B. Celery + Redis (or RabbitMQ) | Mature, widely known. New infrastructure (Redis) to run, secure and back up. Jobs aren't enqueued transactionally with business data, so they can be lost or orphaned unless an outbox is added. |
| C. RQ / Dramatiq + Redis | Lighter than Celery, same Redis and transactional-enqueue issues. |
| D. **PostgreSQL-backed queue** (e.g. **Procrastinate**, or a small in-house `jobs` table claimed with `FOR UPDATE SKIP LOCKED`, the pattern the email outbox already uses) | No new infrastructure. **Jobs are enqueued in the same transaction as the business change** (an application is submitted → its extraction job exists, or neither does). Backups cover the queue. Throughput (thousands of jobs/hour) is far below where Postgres queues struggle. |

**Decision.** **Option D**, run as a separate **worker** service:

```
web (gunicorn, N workers)  ── enqueue in the same DB transaction ──▶  PostgreSQL (jobs table)
                                                                     ▲
worker (1+ processes)  ─────────── claim, run, retry ────────────────┘
scheduler (exactly 1 process, or the worker's periodic-task feature) ── enqueues periodic jobs
```

- Use **Procrastinate** if a short spike in phase 2 confirms it fits the synchronous Flask/SQLAlchemy code (sync task support, periodic tasks, retries, queueing locks).
- Otherwise build the minimal in-house queue (≈300 lines; the email drain already proves the claim pattern).

Either way the API is our own thin wrapper (`jobs.enqueue(name, args, queue, run_at, dedupe_key)`), so the backend can be swapped.

**Consequences**
- **APScheduler is removed from web processes.** The email drain, AUM report, backups, EODs and AI jobs all become jobs. "Send now" enqueues a high-priority drain and returns immediately.
- **Deployment gains a `worker` process** (Docker Compose service / Procfile `worker:` line).
- **Queues with separate concurrency:** `default`, `email`, `eod` (concurrency 1, serialised), `ai` (concurrency N, capped by the API rate limit and cost budget), `reports`.

### 3.1 Business date and batch runs

| Table | Key fields |
|---|---|
| `business_days` | `business_date` (PK), `status` (`open` / `eod_running` / `eod_done` / `eom_done` / `eoy_done`), `opened_at`, `closed_at`, `closed_by` |
| `batch_runs` | `id`, `kind` (`EOD` / `EOM` / `EOY`), `business_date`, `status` (`pending` / `running` / `paused` / `failed` / `completed`), `started_by` (`scheduler` / user), `started_at`, `finished_at` |
| `batch_steps` | `run_id`, `step` (`penalties`, `accrual`, `classification`, `sweeps`, `recurring_fees`, `snapshots`, `checks` …), `status`, `checkpoint` (last processed id), `processed`, `errors`, `log` |

**How runs behave**

| Concern | Behaviour |
|---|---|
| Steps | Idempotent per `(business_date, step, loan)`. Unique keys on accrual rows and journal source keys make re-running harmless. |
| Resume | A failed run resumes from the step checkpoint. |
| Catch-up | If day D isn't closed, D+1 can't start. A scheduler that was down runs the missed days in order. |
| Manual fallback | Admins can start, pause, resume and re-run a step from a Jobs screen (FSD "manual process as back up"). Permission `ops.batch.run`, audited. |
| Blocking exceptions | Open "blocking" risk cases or unresolved suspense above a threshold stop EOM close (not EOD) until resolved or overridden through maker-checker. The FSD asks to "restrict end of day until resolved". We recommend EOM only, so a missing note can't stop interest from accruing (Q-F11). |
| Default timing | EOD runs at **00:30 Nairobi** for the previous business date (no weekends or holidays skipped; interest accrues on calendar days). EOM runs after the last EOD of the month, and closing waits for finance sign-off. |

### 3.2 AI jobs

| Concern | Behaviour |
|---|---|
| Granularity | One job per document page or chunk, then one aggregation job per document (05 §6). |
| Retries | Exponential backoff on HTTP 429/5xx and timeouts. Max 5 attempts, then `failed` with the error shown on the review screen. |
| Ordering | Per-application queueing lock, so pages of one application don't overload the rate limit. Global concurrency from `AI_MAX_CONCURRENCY`. |
| Cost guard | A job checks the application's and the month's spend against `AI_MONTHLY_BUDGET_USD` before calling the API (05 §11). |

---

## 4. Roles and permissions

### ADR-04-4 — Permission-based RBAC with roles as bundles, branch/portfolio scopes and transaction limits

**Context**

Today there are three fixed roles checked by decorators (`@staff_required`, `@admin_required`, `@super_admin_required`), read from the DB on every request. Lending adds **departments** (credit, finance, risk & compliance, investor relations, operations, IT) and the FSD asks for:
- access by user, group, function area and access type (read/create/update/approve);
- per-user and per-role transaction limits;
- departmental maker-checker;
- flagging access to accounts not assigned to the user;
- time-based access;
- printing and export control;
- segregation of duties.

**Options considered**

| Option | Assessment |
|---|---|
| A. Add more fixed roles and decorators (`@credit_officer_required` …) | Explodes combinatorially. Limits and scopes don't fit. |
| B. **Permissions (fine-grained codes) bundled into roles; users get one or more roles; separate tables for branch scope and amount limits** | Standard. Testable. Admin-configurable without deployments. |
| C. Attribute-based policy engine (OPA / Cedar) | Powerful but a new language and service for a small team. B covers the FSD. |

**Decision.** **Option B.** The current roles become built-in bundles so nothing breaks:

| Current role | Becomes bundle | Notes |
|---|---|---|
| `user` | **Operations staff** | Same permissions as today. |
| `admin` | **Operations admin** | Same permissions as today. |
| `super_admin` | **System administrator** | User management, settings, backups, audit. **Recommendation: remove business approval permissions from this bundle** (segregation of duties: IT shouldn't approve withdrawals), after Q-IT10. |

### 4.1 Tables

| Table | Key fields |
|---|---|
| `departments` | `id`, `code` (`OPS` / `CREDIT` / `FIN` / `RISK` / `IR` / `IT`), `name` |
| `permissions` | `code` (PK, e.g. `withdrawal.approve`), `module`, `description`, `sensitive` |
| `roles` | `id`, `code`, `name`, `department_id`, `built_in`, `description` |
| `role_permissions` | `role_id`, `permission_code` |
| `user_roles` | `user_id`, `role_id`, `granted_by`, `granted_at`, `via_change_request_id` |
| `user_branch_scopes` | `user_id`, `branch_id` (or `all_branches = true`) |
| `transaction_limits` | `id`, `subject_type` (`role` / `user`), `subject_id`, `permission_code`, `currency`, `max_per_item`, `max_per_day`, `effective_from` |
| `access_windows` *(optional)* | `role_id`, `weekday`, `from_time`, `to_time` |
| `sod_conflicts` | `permission_a`, `permission_b`, `severity` (`block` / `warn`) |

Role, limit and scope changes are themselves **change requests**, approved by a second system administrator.

### 4.2 Permission catalogue (excerpt; full list grows per phase)

| Module | Permissions |
|---|---|
| Investments | `investor.view`, `investor.create`, `investor.edit`, `investor.close`, `deposit.record`, `deposit.reverse`, `withdrawal.request`, `withdrawal.approve`, `interest.rate.set`, `interest.calculate`, `interest.approve`, `interest.mark_paid`, `statement.generate`, `email.confirm` |
| Parties / KYC | `party.view`, `party.create`, `party.edit`, `party.approve_kyc`, `party.merge`, `watchlist.manage`, `document.view`, `document.view.sensitive`, `document.upload`, `document.delete.approve` |
| AI / screening | `ai.review_fields`, `ai.confirm_fields` (checker), `screening.view`, `screening.rules.edit`, `screening.rules.publish`, `screening.override` |
| Credit | `application.create`, `application.assess`, `loan.approve.l1`, `loan.approve.l2`, `loan.approve.committee`, `loan.disburse.request`, `loan.disburse.approve`, `loan.restructure`, `loan.rate_override`, `loan.write_off.request`, `loan.write_off.approve`, `collateral.manage`, `recoveries.manage` |
| Finance | `gl.view`, `gl.journal.create`, `gl.journal.approve`, `gl.mapping.edit`, `gl.period.close`, `bank.reconcile`, `fixed_assets.manage`, `treasury.manage` |
| Risk / compliance | `risk.view`, `aml.alerts.manage`, `cases.manage`, `audit.view`, `audit.export`, `data_access_log.view` |
| Operations | `ops.batch.run`, `ops.jobs.view`, `report.export.<name>` |
| IT | `user.manage`, `role.manage`, `settings.email`, `settings.ai`, `backup.run` |

### 4.3 Enforcement

| Layer | Behaviour |
|---|---|
| Decorator | `@requires("withdrawal.approve")` replaces role decorators. The user's permissions are loaded from the DB once per request (the same "read from DB every request" guarantee as today) and cached in `g`. The old decorators stay as aliases for one phase. |
| `/me` | Returns permission codes and scopes so the frontend can show or hide UI. **The frontend stays cosmetic**, as `CLAUDE.md` requires. |
| `PASSWORD_CHANGE_REQUIRED` | Unchanged. |
| Tests | Each new endpoint gets an allowed-permission test **and** a missing-permission test, as today's role tests do. |

### 4.4 Transaction limits

- **Approvers:** an approver can decide an amount only if `amount ≤ max_per_item` for that permission (the user's own limit if set, else the highest of their roles' limits). Above the limit the item routes to the next policy level (§1.3).
- **Makers:** limits can also cap what a *maker* may initiate (e.g. a teller can't record a cash deposit above KES 1,000,000 without a supervisor). Daily totals use `max_per_day`.
- **Default amounts** are a management decision (Q-M8).

### 4.5 Data scoping

| Scope | Behaviour |
|---|---|
| Branch | Queries for parties, accounts, loans and applications filter by `user_branch_scopes`. Head-office roles get `all_branches`. |
| Portfolio | Relationship officers see their assigned portfolio by default. The FSD says to **flag** (not necessarily block) access to accounts not assigned to them. Default: allow, write `data_access_logs` with `out_of_portfolio = true`, and show it on a risk report. Blocking is a per-role switch (Q-CO3). |

### 4.6 Related controls from the FSD security list

| Control | Proposed handling |
|---|---|
| Password reuse | Keep the last 5 hashes in `password_history`. |
| Idle timeout | 30 minutes; the frontend logs out. The JWT has a shorter life plus refresh. |
| Single active session per user | Optional (Q-IT5). |
| Time-based access | `access_windows` per role. |
| Export control | `report.export.*` permissions. Every export is already audited. |
| "Restricted copy/paste" | Not enforceable in a browser. Recommend dropping it (Q-IT5). |
| Audit log immutability | A trigger blocking UPDATE/DELETE on `audit_logs` (phase 2), plus read-access logging for customer data (`data_access_logs`). |
| User deletion | Replace `DELETE /users/<id>` with disable-only (Q-IT2), so audit references always resolve. |
