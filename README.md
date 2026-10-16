# Anchorstone Capital Ltd — Statement System

Tracks investor deposits and withdrawals, calculates monthly interest, and
emails investors deposit confirmations, withdrawal confirmations and interest
statements (PDF attached).

```
backend/    Flask + PostgreSQL API
frontend/   React + Vite web app
```

## How it works

- **One account per investor.** Balance = posted deposits − approved withdrawals.
- **Deposits** are recorded by any staff member, take effect immediately, and
  the investor is emailed a confirmation automatically. Mistakes are reversed by
  an admin (with a reason) and are never edited or deleted.
- **Withdrawals** use maker-checker. Staff record a request, and a *different*
  admin approves it (the balance reduces from the effective date, and a
  confirmation email is sent) or rejects it. Requests can't exceed the available
  balance.
- **Interest**: one flat annual rate for everyone, with a dated history of
  changes. It's simple interest on each day's closing balance:
  `balance × rate% ÷ 100 ÷ 365` (fixed 365-day year). Each investor's monthly
  total is rounded once to the cent. Interest is paid out and never added to
  the balance.
- **Monthly run**: after month-end an admin calculates a draft. A different
  admin reviews and approves it, and each investor is then emailed their
  statement. Payouts are tracked as pending until marked paid with a payment
  reference. Approving a month locks it, so nothing can be backdated into it
  afterwards. Approval is refused if any transaction changed since the draft
  was calculated.
- **Withholding tax** is modelled (`tax_rate_percent`, `tax_amount`,
  `net_interest`) but fixed at 0% and hidden on statements until the treatment
  is confirmed.

| Role | Can |
|---|---|
| Staff (`user`) | View everything; add investors; record deposits and withdrawal requests |
| `admin` | + approve/reject withdrawals, reverse deposits, set the rate, calculate/approve interest, mark paid, retry/cancel emails |
| `super_admin` | + users, audit log, backups, email settings |

Roles are checked server-side on every request against the database.

## Accounts

There is no public sign-up. A super admin creates every account under
**Users → Create account** and is shown a one-time temporary password to hand
over. At first sign-in the user must choose their own password before anything
else is reachable (the API refuses all other calls until they do). **Reset
password** works the same way. Disabled accounts can't sign in. Anyone can
change their own password under Settings.

The very first super admin is created from the command line (see Setup).

## Setup

```bash
# Backend
cd backend
python -m venv venv && venv/Scripts/pip install -r requirements.txt   # venv/bin on macOS/Linux
cp .env.example .env            # fill in SECRET_KEY, DATABASE_URI, mail settings
flask --app main db upgrade     # create the schema (Alembic)
flask --app main create-superadmin --name "Your Name" --email you@example.com
flask --app main run --port 4455

# Frontend (second terminal, from the project root)
cd frontend
cp .env.example .env
npm ci
npm run dev                     # http://localhost:5173
```

Production: `APP_ENV=production gunicorn main:app` from `backend/` (see `backend/Dockerfile`). The app
refuses to start in production without `SECRET_KEY` and `DATABASE_URI`. Email
sending needs `MAIL_DEFAULT_SENDER` (or `MAIL_USERNAME`). Without it, emails
stay queued and show the error on the Emails page.

## Tests

```bash
cd backend
venv/Scripts/python -m pytest
```

These run against the real Postgres database in `TEST_DATABASE_URI`, which is
**wiped** on every run, and build the schema from the Alembic migrations.

## Schema changes

From `backend/`: edit the models, then `flask --app main db migrate -m "..."`, review the
generated file in `backend/migrations/versions/`, and run `flask --app main db upgrade`.

## Branding

Light theme: navy `#1A2060`, white, pale lavender `#ECEDFB` for highlights,
Inter for the UI and a bold serif (Playfair Display) for the wordmark only.

- Web app: `frontend/src/styles/globals.css`
- Emails and PDF statements: `backend/app/utils/brand.py`
- Logo: none yet, so the text wordmark is used everywhere. To add one, put the
  file in `frontend/public/` and set `BRAND_LOGO_URL` in
  `frontend/src/lib/constants.ts`; for emails/PDFs save a PNG at
  `backend/assets/logo/anchorstone-logo.png`.

## Not done yet

- `COMPANY_ADDRESS` / `COMPANY_CONTACT` for email and statement footers.
- Withholding tax rate and treatment (pending compliance).
