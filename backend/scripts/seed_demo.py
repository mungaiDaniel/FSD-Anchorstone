"""
Load realistic demo data into a DEMO database (May–September 2026).

    venv\\Scripts\\python scripts\\seed_demo.py            # empty demo DB only
    venv\\Scripts\\python scripts\\seed_demo.py --reset    # wipe the demo DB first

Everything goes through the app's own services (deposits, maker-checker
withdrawals, monthly interest), so every figure is produced exactly as in
real use. Afterwards:

  - May–August interest is approved and paid; past emails are marked sent
    (they were NOT actually sent) so the history looks lived-in.
  - September has NOT been calculated, and one withdrawal is waiting for
    approval, so both can be demonstrated live and will really email.

Investor emails are Gmail "+" aliases of DEMO_INBOX, so every email a client
would receive lands in that one inbox. Refuses to run unless the database
name contains "demo".
"""
import os
import sys
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DEMO_INBOX = os.environ.get("DEMO_INBOX", "danielmungai900@gmail.com")
DEMO_PASSWORD = os.environ.get("DEMO_PASSWORD", "Anchorstone2026")
EAT = timezone(timedelta(hours=3))

STAFF = [  # name, email, role
    ("Daniel Mungai", DEMO_INBOX, "super_admin"),
    ("Wanjiru Kariuki", "wanjiru@anchorstone.demo", "admin"),
    ("Brian Otieno", "brian@anchorstone.demo", "admin"),
    ("Faith Muthoni", "faith@anchorstone.demo", "user"),
]
MAKER = "faith@anchorstone.demo"      # records deposits / withdrawal requests
CHECKER_A = "wanjiru@anchorstone.demo"  # approves withdrawals, calculates interest
CHECKER_B = "brian@anchorstone.demo"    # approves interest

# key, full name, phone, ID, KRA PIN, payout method, bank, account
INVESTORS = [
    ("grace", "Grace Wanjiku Mwangi", "0712 345 678", "28456712", "A012345678K", "mpesa", None, "0712345678"),
    ("peter", "Peter Kamau Njoroge", "0722 118 904", "22981045", "A009876543P", "bank", "KCB Bank", "1145829364"),
    ("aisha", "Aisha Hassan Abdi", "0733 456 120", "31209876", "A015678234M", "mpesa", None, "0733456120"),
    ("john", "John Ochieng Otieno", "0701 223 344", "25678901", "A011223344J", "bank", "Equity Bank", "0180293847561"),
    ("mary", "Mary Achieng Owino", "0745 667 889", "33456789", "A018765432Q", "mpesa", None, "0745667889"),
    ("david", "David Kiprotich Rotich", "0710 998 877", "20345678", "A007654321D", "bank", "Co-operative Bank", "01109283746500"),
    ("fatuma", "Fatuma Said Ali", "0798 112 233", "29871234", "A013579246F", "bank", "NCBA Bank", "1002938475"),
    ("james", "James Mutua Musyoka", "0723 554 466", "24567123", "A010293847R", "bank", "NCBA Bank", "1004857362"),
    ("esther", "Esther Nyambura Kimani", "0757 889 900", "34567890", "A019283746E", "mpesa", None, "0757889900"),
    ("samuel", "Samuel Kipchoge Langat", "0711 445 566", "21234567", "A008172635S", "bank", "Stanbic Bank", "0100003829471"),
    ("lucy", "Lucy Wairimu Gitau", "0768 223 445", "35678123", "A020394857L", "mpesa", None, "0768223445"),
    ("hassan", "Hassan Omar Juma", "0790 334 556", "26789012", "A012938475H", "bank", "Equity Bank", "0180574839201"),
]

# Chronological events. ("dep", date, key, amount, method, reference)
#                       ("wd", requested, key, amount, method, approve_on | "pending" | ("reject", reason))
#                       ("rev", key-of-deposit-reference, reason)
#                       ("month", year, month)  -> calculate, approve, mark paid
EVENTS = [
    ("dep", "2026-05-04", "peter", "1500000", "bank_transfer", "FT26124KCB0417"),
    ("dep", "2026-05-04", "grace", "150000", "mpesa", "SE47K2L9MA"),
    ("dep", "2026-05-12", "john", "800000", "bank_transfer", "FT26132EQB0981"),
    ("dep", "2026-05-15", "aisha", "100000", "mpesa", "SE58P3Q7RB"),
    ("dep", "2026-05-20", "david", "2000000", "bank_transfer", "FT26140COP2207"),
    ("dep", "2026-05-26", "mary", "75000", "mpesa", "SE66T1U4VC"),
    ("month", 2026, 5),
    ("dep", "2026-06-03", "fatuma", "250000", "bank_transfer", "FT26154NCB0332"),
    ("dep", "2026-06-05", "grace", "50000", "mpesa", "SF05W8X2YD"),
    ("dep", "2026-06-10", "james", "1200000", "bank_transfer", "FT26161NCB1145"),
    ("dep", "2026-06-14", "aisha", "50000", "mpesa", "SF14Z6A3BE"),
    ("dep", "2026-06-14", "aisha", "50000", "mpesa", "SF14Z6A3BF"),
    ("rev", "SF14Z6A3BF", "Entered twice — duplicate of M-Pesa receipt SF14Z6A3BE."),
    ("wd", "2026-06-18", "peter", "300000", "bank_transfer", "2026-06-19"),
    ("dep", "2026-06-24", "esther", "400000", "bank_transfer", "FT26175EQB3310"),
    ("month", 2026, 6),
    ("dep", "2026-07-02", "samuel", "3500000", "bank_transfer", "FT26183SBK0029"),
    ("dep", "2026-07-08", "mary", "75000", "mpesa", "SG08C9D1EG"),
    ("dep", "2026-07-11", "john", "200000", "bank_transfer", "FT26192EQB1876"),
    ("wd", "2026-07-15", "david", "500000", "bank_transfer", "2026-07-16"),
    ("dep", "2026-07-22", "lucy", "120000", "mpesa", "SG22F4G6HH"),
    ("dep", "2026-07-29", "grace", "100000", "mpesa", "SG29J7K2LI"),
    ("month", 2026, 7),
    ("dep", "2026-08-04", "hassan", "600000", "bank_transfer", "FT26216EQB0563"),
    ("dep", "2026-08-06", "esther", "100000", "mpesa", "SH06M3N8PJ"),
    ("wd", "2026-08-12", "fatuma", "50000", "bank_transfer", "2026-08-12"),
    ("dep", "2026-08-19", "james", "300000", "bank_transfer", "FT26231NCB2290"),
    ("wd", "2026-08-20", "hassan", "200000", "bank_transfer", ("reject", "Investor cancelled the request by phone on 21 Aug.")),
    ("dep", "2026-08-25", "peter", "250000", "bank_transfer", "FT26237KCB0815"),
    ("month", 2026, 8),
    ("dep", "2026-09-01", "samuel", "500000", "bank_transfer", "FT26244SBK0144"),
    ("dep", "2026-09-09", "aisha", "75000", "mpesa", "SI09Q5R1SK"),
    ("wd", "2026-09-12", "john", "150000", "bank_transfer", "2026-09-14"),
    ("dep", "2026-09-16", "lucy", "80000", "mpesa", "SI16T8U3VL"),
    ("dep", "2026-09-23", "mary", "50000", "mpesa", "SI23W2X7YM"),
    ("wd", "2026-09-28", "grace", "100000", "mpesa", "2026-09-29"),
    ("wd", "2026-09-30", "james", "200000", "bank_transfer", "pending"),  # live demo: approve it
]


def d(s: str) -> date:
    return date.fromisoformat(s)


def at(day: date, hour: int = 10, minute: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute), EAT).astimezone(timezone.utc)


def main(reset: bool) -> None:
    from sqlalchemy import text
    from sqlalchemy.engine import make_url

    from main import app
    from app.Admin.model import User
    from app.database.database import db
    from app.Emails.model import STATUS_QUEUED, STATUS_SENT, OutboxEmail
    from app.Interest import service as interest
    from app.Interest.model import InterestPayout, InterestPeriod, InterestRate
    from app.Investors.model import Investor
    from app.Investors.service import create_investor
    from app.Transactions import service as tx
    from app.Transactions.model import Deposit, Withdrawal
    from app.utils.dates import month_bounds

    with app.app_context():
        db_name = make_url(app.config["SQLALCHEMY_DATABASE_URI"]).database or ""
        if "demo" not in db_name:
            sys.exit(f"Refusing to seed '{db_name}': the database name must contain 'demo'.")

        if reset:
            db.session.execute(text(
                'TRUNCATE "user", investors, deposits, withdrawals, interest_rates, interest_periods, '
                "interest_payouts, email_outbox, audit_logs, account_holds RESTART IDENTITY CASCADE"))
            db.session.execute(text("ALTER SEQUENCE investor_client_code_seq RESTART WITH 1"))
            db.session.commit()
        elif db.session.query(Investor.id).first() is not None:
            sys.exit("The demo database already has investors. Re-run with --reset to start over.")

        # Staff
        for name, email, role in STAFF:
            user = User.query.filter(db.func.lower(User.email) == email.lower()).first() or User(name=name, email=email)
            user.password = User.generate_password_hash(DEMO_PASSWORD)
            user.role, user.status, user.must_change_password = role, "active", False
            db.session.add(user)
        db.session.commit()

        # Interest rate history
        interest.set_rate({"rate_percent": "11", "effective_from": "2026-05-01", "note": "Launch rate"}, CHECKER_A)
        interest.set_rate({"rate_percent": "12", "effective_from": "2026-08-01", "note": "Board-approved increase"}, CHECKER_A)
        for r in InterestRate.query.all():
            r.created_at = at(r.effective_from - timedelta(days=3), 15)

        # Investors (created the day of their first deposit)
        first_dep = {}
        for e in EVENTS:
            if e[0] == "dep":
                first_dep.setdefault(e[2], d(e[1]))
        inv = {}
        local, domain = DEMO_INBOX.split("@")
        for key, name, phone, id_no, pin, method, bank, account in INVESTORS:
            i = create_investor({
                "full_name": name, "email": f"{local}+{key}@{domain}", "phone": phone, "id_number": id_no,
                "kra_pin": pin, "payout_method": method, "bank_name": bank, "payout_account": account,
            }, MAKER)
            i.created_at = at(first_dep[key], 9, 30)
            inv[key] = i.id
        db.session.commit()

        # Transactions and monthly interest, in date order
        for e in EVENTS:
            kind = e[0]
            if kind == "dep":
                _, day, key, amount, method, ref = e
                dep = tx.record_deposit({"investor_id": inv[key], "amount": amount, "value_date": day,
                                         "method": method, "reference": ref}, MAKER)
                dep.created_at = at(d(day), 11)
            elif kind == "rev":
                dep = Deposit.query.filter_by(reference=e[1]).one()
                tx.reverse_deposit(dep.id, {"reason": e[2]}, CHECKER_A)
                dep.reversed_at = at(dep.value_date, 16)
            elif kind == "wd":
                _, day, key, amount, method, decision = e
                w = tx.request_withdrawal({"investor_id": inv[key], "amount": amount, "requested_date": day,
                                           "method": method}, MAKER)
                w.created_at = at(d(day), 12)
                if decision == "pending":
                    pass
                elif isinstance(decision, tuple):
                    tx.reject_withdrawal(w.id, {"reason": decision[1]}, CHECKER_A)
                    w.decided_at = at(d(day) + timedelta(days=1), 10)
                else:
                    ref = f"EFT{d(decision):%y%m%d}{w.id:03d}" if method == "bank_transfer" else f"SQ{w.id:02d}{d(decision):%m%d}ZK"
                    tx.approve_withdrawal(w.id, {"value_date": decision, "payment_reference": ref}, CHECKER_A)
                    w.decided_at = at(d(decision), 14)
            elif kind == "month":
                _, year, month = e
                period = interest.calculate_period({"year": year, "month": month}, CHECKER_A)
                interest.approve_period(period.id, CHECKER_B)
                payouts = period.payouts.all()
                interest.mark_payouts_paid(period.id, {"payments": [
                    {"payout_id": p.id,
                     "reference": (f"SQ{p.id:03d}{month:02d}PAY" if p.investor.payout_method == "mpesa"
                                   else f"EFT{year % 100}{month:02d}{p.id:04d}")}
                    for p in payouts]}, CHECKER_A)
                _, end = month_bounds(year, month)
                period.calculated_at = at(end + timedelta(days=2), 9)
                period.approved_at = at(end + timedelta(days=2), 15)
                period.paid_at = at(end + timedelta(days=5), 11)
                for p in payouts:
                    p.paid_at = period.paid_at
            db.session.commit()

        # Past emails: backdate and mark sent (history only — nothing was actually emailed).
        for email in OutboxEmail.query.filter(OutboxEmail.status == STATUS_QUEUED).all():
            when = None
            if email.deposit_id:
                when = db.session.get(Deposit, email.deposit_id).created_at + timedelta(minutes=3)
            elif email.withdrawal_id:
                when = db.session.get(Withdrawal, email.withdrawal_id).decided_at + timedelta(minutes=3)
            elif email.payout_id:
                when = db.session.get(InterestPayout, email.payout_id).period.approved_at + timedelta(minutes=5)
            email.queued_at = when
            email.status, email.sent_at, email.attempts = STATUS_SENT, when + timedelta(minutes=2), 1
        db.session.commit()

        n_inv = Investor.query.count()
        n_dep = Deposit.query.count()
        n_wd = Withdrawal.query.count()
        n_per = InterestPeriod.query.count()
        print(f"Seeded {n_inv} investors, {n_dep} deposits, {n_wd} withdrawals, {n_per} paid interest months.")
        print(f"Investor emails go to {DEMO_INBOX} (as +aliases).")
        print(f"Demo sign-ins (password for all: {DEMO_PASSWORD}):")
        for name, email, role in STAFF:
            print(f"  {role:<12} {name:<18} {email}")


if __name__ == "__main__":
    main(reset="--reset" in sys.argv)
