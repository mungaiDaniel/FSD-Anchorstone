# Anchorstone Capital Ltd — Statement System

This is internal staff software for a licensed investment company in Nairobi. It records
investor deposits and withdrawals, calculates monthly interest, and emails confirmations
and statements. `backend/` is Flask + PostgreSQL; `frontend/` is React + Vite + TypeScript.
The business rules are in `README.md`.

`docs/fsd.md` is a Functional Specification Document written for **another lender**.
Use it as a reference for structure and good practice only. Adapt anything you take
from it to Anchorstone, and never copy its product names, vendor, branches or rates.

When a business rule or brand value is ambiguous, **ask the user**. Don't guess.
Propose a recommended default.

## Non-negotiable conventions

### Money

- **Money is `Decimal`, end to end. Never `float`.** Currency is **KES** only.
- **Storage:** amounts are `NUMERIC(20,2)`; rates (annual %) are `NUMERIC(7,4)`.
- **Input** is parsed in `backend/app/utils/money.py`:
  - `parse_amount` requires an amount > 0 with at most 2 decimal places. Commas are allowed. Extra decimals are **rejected, not rounded**.
  - `parse_rate_percent` requires 0–100 with at most 4 decimal places.
- **Rounding** is `round_money()`, which rounds to the cent with `ROUND_HALF_UP`. It happens in the service layer at these points only:
  - **Interest:** each day's interest is summed at full precision, and the investor's month total is rounded **once** (`app/Interest/service.py`). Never round per day.
  - **Payout figures:** the average daily balance is rounded to the cent, and the effective rate is quantized to 4 decimal places.
  - **Withholding tax:** `round_money(gross × tax_rate ÷ 100)` per payout. `net = gross − tax` is enforced by a DB check constraint. The tax rate is the setting `investments.wht_rate_percent` in force on the month's last day: 0% and hidden until compliance confirms the treatment.
- **JSON** sends money as strings via `as_str()` (e.g. `"1234.50"`). Text formatting uses `fmt_kes()`.
- **Frontend:** amounts are sent as strings. `Number()` is used only for display and UI pre-checks; the server is the authority. Excel exports convert to float only at the spreadsheet cell (`app/Reports/excel.py`).

### Dates

- **"Today" means Nairobi time.** Use `today_eat()` from `app/utils/dates.py` (fixed UTC+3, same as Africa/Nairobi, no DST). It applies to value dates, the no-future-dates rule, month-end and "as of" figures. Never use `date.today()` or the server's local date.
- **Timestamps** are stored timezone-aware in UTC (`utcnow()`).
- **The scheduler runs in UTC**, so convert (07:00 Nairobi = 04:00 UTC).

### Background work runs in the worker, never in web processes

- Jobs are rows in `jobs` (`app/Jobs`), run by `flask --app main worker`. Register a task with `@task("name", queue=…)` in `app/Jobs/tasks.py` and call `enqueue(name, args)` **without committing**: the caller commits it with the business change.
- Periodic work is a `Periodic` entry in `app/Jobs/registry.py`. Each slot is enqueued once (unique `dedupe_key`) however many processes run, and missed slots catch up (`latest` or `each`).
- Tasks must be safe to run again: a job whose worker dies is reclaimed and re-run.
- **Frontend:** the equivalent is `todayISO()`.
- **Tests** pin "today" to 2026-10-05. Any module that imports `today_eat` must be added to `_DATED_MODULES` in `backend/tests/conftest.py`.

### Maker-checker

- **The person who creates a record can never approve it.** The rule is implemented once, in `app/Approvals/policy.py`, and enforced again by the database.
- **Records that are requests by nature** (withdrawals, interest periods) keep their own status and call `assert_can_decide(request_type, maker_email=…, actor_email=…, amount=…, branch_id=…, maker_message="Maker-checker: …")`. It checks maker ≠ checker (emails, case-insensitive), the approval policy, the level's permission, the approver's transaction limit and branch scope. CHECK constraints back it up:
  - withdrawals (`requested_by` ≠ `decided_by`)
  - monthly interest (`calculated_by` ≠ `approved_by`)
- **Changes to existing data** (access, settings, document destruction, later party and loan edits) are **change requests** (`app/Approvals`): a handler with `validate` / `apply` / `describe` / `base_version`, registered with `@register` and loaded in `load_handlers()`. Approval policies (`approval_policies`) choose the levels by request type and amount. A DB trigger refuses a decision by the maker; a unique index stops one person approving twice.
- Every new approval step must follow the same pattern. Write a test for both the refused and the allowed path, including a raw-SQL test that the database refuses maker = checker.

### Posted records are never edited or deleted

- **Deposits** go `posted → reversed`. A reversal requires a reason (admin only) and records `reversed_by` and `reversed_at`.
- **Withdrawals** go `pending → approved | rejected`. Rejection requires a reason. Only an approved withdrawal moves the balance, from its value date.
- **Interest periods** go `draft → approved → paid`.
  - Only a **draft** may be recalculated or discarded.
  - Approval locks every date up to the period end (`assert_not_locked`). Nothing may be backdated into an approved month.
- **Payouts** are marked paid with a payment reference.
- **Emails** are cancelled, never deleted.
- **Enforcement:**
  - Status values use `CheckConstraint`s.
  - Financial foreign keys use `ondelete="RESTRICT"`.
  - Balance-affecting writes take `lock_investor()` (`SELECT … FOR UPDATE`) first.
- **The balance has one definition:** `app/Transactions/ledger.py` (posted deposits − approved withdrawals, by value date). Interest is paid out and never added to the balance.

### Business rules are settings, not constants

- Values the client may change (limits, rates, periods, retention …) live in `app/Settings/registry.py` and are read with `app.Settings.business.get(key, as_of=…, scope=…)`. Never hard-code one.
- Each change is a new immutable row in `setting_versions`, made through a `settings.change` change request (`settings.change_security`, two approvers, for security keys). Nothing is backdated.
- Event-dated values (`investments.wht_rate_percent`) are read **as of the event's business date**, so recalculating a past month reproduces it.
- A new key needs a registry entry **and** a migration seeding version 1 with its source and evidence. `docs/architecture/08-working-assumptions.md` says what each default is and who confirms it.

### Every business action is audited

- Call `create_audit_log(ACTION, target_type=…, target_id=…, target_name=…, description=…, old_value=…, new_value=…)` from `app/utils/audit_log.py` **before** `db.session.commit()`, in the same transaction as the change it describes.
- It adds and flushes the row but never commits. If the audit write fails, the error propagates and the whole action rolls back. Flush first if `target_id` is a new row's id.
- It records who did it (from `g.current_user`), the IP (`request.remote_addr`; `X-Forwarded-For` is trusted only through `ProxyFix` for `TRUSTED_PROXY_COUNT` proxies), the user agent, and old/new values as JSON.
- Action names are `UPPER_SNAKE` verbs (`APPROVE_WITHDRAWAL`).
- Report exports are audited too.
- Background jobs pass `actor_user_email="scheduler"`.
- Never put passwords or secrets in `old_value`/`new_value`.

### All email goes through the outbox

- Investor and management emails are rows in `email_outbox` (`app/Emails/model.py`).
- The `queue_*` functions in `app/Emails/composer.py` add the row **without committing**. The caller commits it together with the business change.
- The worker's `email.drain` job (`app/Jobs/tasks.py` → `drain_queue`) sends only `queued` rows. It claims them with `SKIP LOCKED` and retries up to the `email.max_attempts` setting (3).
- Anything an admin must review starts as `pending` (Confirm → `queued`, Suppress → `cancelled`).
- Attachments that must not change are stored in `email_attachments` when the email is created.
- Unique constraints stop a deposit, withdrawal, payout or request key from being emailed twice.
- Bodies are plain text, rendered into the branded HTML template at send time. Lines starting with "•" become bullets; short ALL-CAPS lines become headings.
- **Never call `mail.send` from feature code.** The only exception is the SMTP test button in `app/Settings/route.py`.

### Permissions come from the database on every request

- Every route uses one decorator from `app/auth.py`: `@requires("<permission>")` or `@password_change_endpoint`. Checks that depend on the request use `require_permission()` / `has_permission()`.
- Permissions are bundled into roles (`app/Access`). A user's permissions are their primary built-in role (`user.role`) plus any extra roles in `user_roles`.
- The user, roles and status are re-read from the DB on each call. JWT claims are never trusted for authorization.
- Built-in roles: `user` â†’ Operations staff âŠ‚ `admin` â†’ Operations admin âŠ‚ `super_admin` â†’ System administrator. They reproduce the old role rules exactly (`tests/test_permissions.py`).
- A new endpoint gets a new permission in a migration, granted to the right built-in roles, and a row in the route table of `tests/test_permissions.py`.
- Amount-limited permissions (`withdrawal.approve`, `interest.approve` â€¦) are capped by `transaction_limits`; no limit row means no amount can be decided.
- An account with `must_change_password` gets 403 `PASSWORD_CHANGE_REQUIRED` everywhere else.
- Inside a route, use `current_user()` and `actor_email()`.
- Frontend route guards and `RoleGate` only hide UI. They are never the security boundary.

### Other fixed rules

- **PostgreSQL only.** No SQLite anywhere, including tests.
- **Test databases:**
  - The test DB name must contain `test`, because it is wiped on every run.
  - The demo seed refuses any DB name without `demo`. `--reset` also needs `--i-understand-this-deletes-data` and a DB name ending in `_demo` or `_test`; it rebuilds the schema with the migrations and forces `MAIL_SUPPRESS_SEND`.
- **Uploaded documents** go through `app/Documents/service.py` only: AES-256-GCM with a per-file key wrapped by `DOCUMENT_KEK` (not `SECRET_KEY`), bytes in a `DocumentStore`, every read logged in `data_access_logs`. Never serve a store URL or the raw bytes, and never delete a document row: destroying one is a `document.destroy` change request (the key and blob go; the row stays).
- `MAIL_SUPPRESS_SEND=true` means nothing is actually sent. Check it before pointing at real investor data.
- **No public sign-up:**
  - Super admins create accounts with a one-time temporary password.
  - Account status is `active | disabled`.
- **Brand** is light theme only: navy `#1A2060`.
  - Keep `frontend/src/styles/globals.css` and `backend/app/utils/brand.py` in step.
  - There's no logo yet. The drop-in points are `BRAND_LOGO_URL` in `frontend/src/lib/constants.ts` and `backend/assets/logo/anchorstone-logo.png`.

## Layout: new modules follow this structure

### Backend: `backend/app/<Module>/` (PascalCase folder)

- `__init__.py`: empty.
- `model.py`:
  - Classes are `class X(Base, db.Model)`, using `Base` from `backend/base_model.py`, which adds `date_created`/`date_updated`.
  - Status sets are constants plus `CheckConstraint`s.
  - `to_dict()` serializes money with `as_str` and dates with `iso`.
- `service.py`:
  - All business rules live here.
  - Raise `ValidationError` / `Forbidden` / `NotFound` / `Conflict` from `app/utils/http.py`. Never return error tuples.
  - Make the change, write the audit entry, then commit both together.
- `route.py`:
  - A `Blueprint("<name>_v1", __name__)` with paths `/api/v1/...`.
  - Keep routes thin: parse the request, call the service, and `return ok(data, "Message.", status)`.
  - Paginate lists with `page_args` / `paginate`.
- **Register the module in `backend/main.py`:** import the models in `_import_models()` and add the blueprint to the tuple in `create_app()`.
- **Every schema change gets an Alembic migration** in `backend/migrations/versions/`. Review it before upgrading. Never edit an applied migration.
- **Shared helpers** are in `app/utils/`: `money`, `dates`, `http`, `audit_log`, `pdf_generator`, `email_template`, `brand`, `crypto`.
- **Tests** go in `backend/tests/test_<area>.py`. Use the fixtures in `conftest.py`: `staff`, `admin1`, `admin2`, `superadmin`, `make_investor`, `deposit`, `withdraw`, `rate`.

### Frontend: `frontend/src/`

- **Pages:** `pages/<area>/<Name>Page.tsx`, lazy-loaded in `routes/index.tsx` under `ProtectedRoute` / `AdminRoute` / `SuperAdminRoute`.
- **Constants:** URL paths go in `lib/constants.ts` (`ROUTES`), API paths in `API`, and response types in `lib/types.ts`.
- **API calls:** only through `services/index.ts`, which uses the axios instance in `services/api.ts`. That instance adds the JWT and handles 401 and `PASSWORD_CHANGE_REQUIRED`.
- **Components** go in `components/<kind>/`. Toasts use `sonner`; icons use `lucide-react`. Use the CSS variables from `globals.css`, not hard-coded colours.
- **Styling uses both frameworks, each for its own job:**
  - **Bootstrap** for components and layout: `btn`, `form-control`, `table`, `card`, `row`/`col-*`, `d-flex`.
  - **Tailwind** for finishing touches: shadows, gradients, hover and transition effects, fine spacing and type sizes.
  - **Every Tailwind class has the `tw:` prefix** (`tw:shadow-lg`, `tw:sm:text-xl`, `tw:hover:bg-bg-tint`). An unprefixed Tailwind name does nothing.
  - **Brand tokens** work as Tailwind colours: `tw:bg-brand-400`, `tw:text-text-tertiary`, `tw:bg-warning-bg`.
  - **Cascade:** Bootstrap and the app's own CSS share the `ui` layer, and `tw:` utilities sit above it, so a `tw:` class overrides a component style. Bootstrap's `!important` utilities (`.shadow`, `.d-flex` …) still win, so don't combine one with a `tw:` class for the same property.
  - **`cn()`** only joins class names (`clsx`). There is no `tailwind-merge`.
- **List pages reuse the shared table pieces** in `components/ui/Page.tsx`:
  - `LoadingRow` (placeholder rows), `EmptyState` (icon, title, message, action) and `Pagination`.
  - `SearchField` for search boxes and `SegmentedTabs` for a table's main filter.
  - `InvestorCell` (initials, name, client code) and `Actor` (who did it, short form).
  - Row actions use `app-btn-ghost` or `app-btn-ghost-danger` so long tables aren't a wall of buttons.
- **List loads use `useRequestGuard`** (`lib/useRequestGuard.ts`), so a slow response for an old filter can't replace the rows on screen.

## Commands

The machine is Windows: run these in Git Bash, or use `\` paths in PowerShell. The backend `.env` lives in `backend/`.

```bash
# Backend — from backend/
venv/Scripts/python -m pip install -r requirements.txt
venv/Scripts/python -m flask --app main db upgrade                 # apply migrations
venv/Scripts/python -m flask --app main db migrate -m "describe"   # new migration (then review it)
venv/Scripts/python -m flask --app main create-superadmin          # first account
venv/Scripts/python -m flask --app main run --port 4455            # dev API on :4455
venv/Scripts/python -m pytest                                      # all tests (wipes TEST_DATABASE_URI)
venv/Scripts/python -m pytest tests/test_interest.py -k mark_paid  # a subset
venv/Scripts/python scripts/seed_demo.py --reset --i-understand-this-deletes-data  # wipe + reseed demo (DB name ends in _demo)

# Frontend — from frontend/
npm ci
npm run dev        # http://localhost:5173 (API from VITE_API_URL, default http://localhost:4455/api/v1)
npx tsc -b         # type-check
npm run build      # type-check + production build
```

There are no frontend tests and no ESLint config yet, so `npm test` and `npm run lint` don't verify anything.

## Definition of done for every phase

- **The full backend suite passes:** `venv/Scripts/python -m pytest` is green.
- **The frontend is clean:** `npx tsc -b` reports no errors, and `npm run build` succeeds when the frontend changed.
- **New behaviour has new tests in the same phase.** Cover the allowed path *and* the refusals: wrong role, maker = checker, invalid input, locked period, duplicates.
- **A phase isn't finished while anything fails.** Report failures with their output. Never skip, delete or weaken a test to get green.
