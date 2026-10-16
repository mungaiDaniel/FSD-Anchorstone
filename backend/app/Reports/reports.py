"""
The seven Excel reports. Each builder takes the request's query arguments and
returns a Report (file name, bytes, a one-line description of what was
exported, row count) — the route streams it and writes the audit entry.
"""
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import func

from app.database.database import db
from app.Emails.composer import METHOD_LABELS
from app.Emails.model import OutboxEmail
from app.Interest.model import LOCKED_PERIOD_STATUSES, InterestPayout, InterestPeriod
from app.Investors.model import INVESTOR_STATUSES, Investor
from app.Reports.excel import Col, build_workbook, fmt_range
from app.Transactions.ledger import investor_totals
from app.Transactions.model import (
    DEPOSIT_POSTED,
    DEPOSIT_REVERSED,
    WITHDRAWAL_APPROVED,
    WITHDRAWAL_PENDING,
    WITHDRAWAL_REJECTED,
    Deposit,
    Withdrawal,
)
from app.utils.dates import EAT, month_bounds, parse_date, today_eat, utcnow
from app.utils.http import ValidationError
from app.utils.money import ZERO

MAX_ROWS = 100_000
WITHDRAWAL_STATUSES = (WITHDRAWAL_PENDING, WITHDRAWAL_APPROVED, WITHDRAWAL_REJECTED)
DEPOSIT_STATUSES = (DEPOSIT_POSTED, DEPOSIT_REVERSED)

EMAIL_TYPE_LABELS = {
    "DEPOSIT_CONFIRMATION": "Deposit confirmation",
    "WITHDRAWAL_CONFIRMATION": "Withdrawal confirmation",
    "INTEREST_STATEMENT": "Interest statement",
    "ACCOUNT_STATEMENT": "Account statement",
    "AUM_REPORT": "Monthly AUM summary",
}
EMAIL_STATUS_LABELS = {
    "pending": "Awaiting confirmation",
    "queued": "Queued",
    "sending": "Sending",
    "sent": "Sent",
    "failed": "Failed",
    "cancelled": "Cancelled",
}


@dataclass
class Report:
    filename: str
    data: bytes
    description: str
    rows: int


def _stamp() -> str:
    return f"Generated {utcnow().astimezone(EAT):%d %b %Y %H:%M} (Nairobi time)"


def _range(args) -> tuple[date | None, date | None]:
    start = parse_date(args.get("from"), "from", required=False)
    end = parse_date(args.get("to"), "to", required=False)
    if start and end and start > end:
        raise ValidationError("The start date must be on or before the end date.")
    return start, end


def _suffix(start, end) -> str:
    if start or end:
        return f"_{start or 'start'}_to_{end or today_eat()}"
    return f"_{today_eat()}"


def _name(inv: Investor | None) -> tuple[str, str]:
    return (inv.client_code, inv.full_name) if inv else ("", "")


# 1 ── Investors ───────────────────────────────────────────────────────────


def investors_report(args) -> Report:
    status = args.get("status") or None
    if status and status not in INVESTOR_STATUSES:
        raise ValidationError(f"status must be one of: {', '.join(INVESTOR_STATUSES)}.")
    q = Investor.query.order_by(Investor.client_code)
    if status:
        q = q.filter(Investor.status == status)
    rows, sums = [], defaultdict(Decimal)
    for inv in q.limit(MAX_ROWS):
        t = investor_totals(inv.id)
        for k in ("balance", "total_deposited", "total_withdrawn", "interest_paid", "interest_payable"):
            sums[k] += t[k]
        rows.append([inv.client_code, inv.full_name, inv.email, inv.phone, inv.status.title(),
                     t["balance"], t["total_deposited"], t["total_withdrawn"], t["interest_paid"],
                     t["interest_payable"], inv.created_at])
    cols = [Col("Client code", 14), Col("Name", 28), Col("Email", 34), Col("Phone", 16), Col("Status", 10),
            Col("Balance (KES)", 18, "money"), Col("Total deposited (KES)", 20, "money"),
            Col("Total withdrawn (KES)", 20, "money"), Col("Interest paid (KES)", 18, "money"),
            Col("Interest due (KES)", 18, "money"), Col("Opened", 14, "date")]
    scope = f"{status.title()} investors" if status else "All investors"
    data = build_workbook("Investors", [f"{scope} · balances as of {today_eat():%d %b %Y}", _stamp()], cols, rows,
                          {"label": f"Total ({len(rows)} investors)", 5: sums["balance"], 6: sums["total_deposited"],
                           7: sums["total_withdrawn"], 8: sums["interest_paid"], 9: sums["interest_payable"]},
                          "Investors")
    return Report(f"Anchorstone_investors_{today_eat()}.xlsx", data, scope, len(rows))


# 2 ── Deposits ────────────────────────────────────────────────────────────


def deposits_report(args) -> Report:
    start, end = _range(args)
    status = args.get("status") or None
    if status and status not in DEPOSIT_STATUSES:
        raise ValidationError(f"status must be one of: {', '.join(DEPOSIT_STATUSES)}.")
    q = Deposit.query.order_by(Deposit.value_date, Deposit.id)
    if start:
        q = q.filter(Deposit.value_date >= start)
    if end:
        q = q.filter(Deposit.value_date <= end)
    if status:
        q = q.filter(Deposit.status == status)
    rows, posted, n_posted = [], ZERO, 0
    for d in q.limit(MAX_ROWS):
        code, name = _name(d.investor)
        if d.status == DEPOSIT_POSTED:
            posted += Decimal(d.amount)
            n_posted += 1
        rows.append([d.value_date, code, name, d.reference, METHOD_LABELS.get(d.method, d.method),
                     Decimal(d.amount), d.status.title(), d.recorded_by, d.created_at,
                     d.reversed_by, d.reversal_reason])
    cols = [Col("Date received", 14, "date"), Col("Client code", 14), Col("Investor", 28), Col("Reference", 20),
            Col("Method", 14), Col("Amount (KES)", 18, "money"), Col("Status", 11), Col("Recorded by", 28),
            Col("Recorded at", 18, "datetime"), Col("Reversed by", 26), Col("Reversal reason", 36)]
    desc = fmt_range(start, end) + (f" · {status} only" if status else "")
    data = build_workbook("Deposits", [desc, _stamp()], cols, rows,
                          {"label": f"Total posted ({n_posted} deposits)", 5: posted}, "Deposits")
    return Report(f"Anchorstone_deposits{_suffix(start, end)}.xlsx", data, desc, len(rows))


# 3 ── Withdrawals ─────────────────────────────────────────────────────────


def withdrawals_report(args) -> Report:
    start, end = _range(args)
    status = args.get("status") or None
    if status and status not in WITHDRAWAL_STATUSES:
        raise ValidationError(f"status must be one of: {', '.join(WITHDRAWAL_STATUSES)}.")
    # Approved withdrawals are dated by their effective date; others by the request date.
    when = func.coalesce(Withdrawal.value_date, Withdrawal.requested_date)
    q = Withdrawal.query.order_by(when, Withdrawal.id)
    if start:
        q = q.filter(when >= start)
    if end:
        q = q.filter(when <= end)
    if status:
        q = q.filter(Withdrawal.status == status)
    rows, approved, n_approved = [], ZERO, 0
    for w in q.limit(MAX_ROWS):
        code, name = _name(w.investor)
        if w.status == WITHDRAWAL_APPROVED:
            approved += Decimal(w.amount)
            n_approved += 1
        rows.append([w.requested_date, w.value_date, code, name, w.payment_reference,
                     METHOD_LABELS.get(w.method, w.method), Decimal(w.amount), w.status.title(),
                     w.requested_by, w.decided_by, w.decided_at, w.rejection_reason])
    cols = [Col("Requested", 13, "date"), Col("Effective date", 14, "date"), Col("Client code", 14),
            Col("Investor", 28), Col("Payment reference", 20), Col("Method", 14), Col("Amount (KES)", 18, "money"),
            Col("Status", 11), Col("Recorded by", 28), Col("Approved / rejected by", 28),
            Col("Decided at", 18, "datetime"), Col("Rejection reason", 34)]
    desc = fmt_range(start, end) + (f" · {status} only" if status else "")
    data = build_workbook("Withdrawals", [desc, "Approved withdrawals are dated by their effective date.", _stamp()],
                          cols, rows, {"label": f"Total approved ({n_approved} withdrawals)", 6: approved},
                          "Withdrawals")
    return Report(f"Anchorstone_withdrawals{_suffix(start, end)}.xlsx", data, desc, len(rows))


# 4 ── Interest payouts ────────────────────────────────────────────────────


def interest_report(args) -> Report:
    q = InterestPeriod.query.filter(InterestPeriod.status.in_(LOCKED_PERIOD_STATUSES))
    if args.get("period_id"):
        try:
            q = q.filter(InterestPeriod.id == int(args["period_id"]))
        except ValueError:
            raise ValidationError("period_id must be a number.")
        start = end = None
    else:
        start, end = _range(args)
        if start:
            q = q.filter(InterestPeriod.period_end >= start)
        if end:
            q = q.filter(InterestPeriod.period_start <= end)
    periods = q.order_by(InterestPeriod.period_start).all()
    if args.get("period_id") and not periods:
        raise ValidationError("That month hasn't been approved, so there is nothing to export yet.")

    rows, total = [], ZERO
    for period in periods:
        payouts = (period.payouts.join(Investor, Investor.id == InterestPayout.investor_id)
                   .order_by(Investor.client_code).all())
        for p in payouts:
            total += Decimal(p.net_interest)
            rows.append([period.label, p.investor.client_code, p.investor.full_name, Decimal(p.opening_balance),
                         Decimal(p.closing_balance), Decimal(p.average_daily_balance), p.days, Decimal(p.rate_percent),
                         Decimal(p.net_interest), p.status.title(), p.paid_at, p.payment_reference,
                         period.calculated_by, period.approved_by])
    cols = [Col("Month", 15), Col("Client code", 14), Col("Investor", 28), Col("Opening balance (KES)", 20, "money"),
            Col("Closing balance (KES)", 20, "money"), Col("Average daily balance (KES)", 24, "money"),
            Col("Days", 7, "int"), Col("Rate (p.a.)", 11, "rate"), Col("Interest (KES)", 16, "money"),
            Col("Payment", 10), Col("Paid on", 16, "datetime"), Col("Payment reference", 20),
            Col("Calculated by", 28), Col("Approved by", 28)]
    if args.get("period_id"):
        desc = periods[0].label
        fname = f"Anchorstone_interest_{periods[0].period_start:%Y-%m}.xlsx"
    else:
        desc = (f"{periods[0].label} to {periods[-1].label}" if periods else fmt_range(start, end))
        fname = f"Anchorstone_interest{_suffix(start, end)}.xlsx"
    data = build_workbook("Interest payouts", [f"Approved months: {desc}", _stamp()], cols, rows,
                          {"label": f"Total ({len(periods)} month(s), {len(rows)} payouts)", 8: total}, "Interest")
    return Report(fname, data, desc, len(rows))


# 5 ── Portfolio / AUM ─────────────────────────────────────────────────────


def _add_months(d: date, n: int) -> date:
    m = d.month - 1 + n
    return date(d.year + m // 12, m % 12 + 1, 1)


def aum_series(through: date | None = None) -> list[dict]:
    """Funds under management at each month end (or `through` for the last,
    unfinished month), from the month of the first deposit."""
    through = through or today_eat()
    events = defaultdict(list)  # date -> [(investor_id, signed amount)]
    deposits_by_month = defaultdict(Decimal)
    withdrawals_by_month = defaultdict(Decimal)
    for inv_id, d, amt in db.session.query(Deposit.investor_id, Deposit.value_date, Deposit.amount).filter(
            Deposit.status == DEPOSIT_POSTED, Deposit.value_date <= through):
        events[d].append((inv_id, Decimal(amt)))
        deposits_by_month[d.replace(day=1)] += Decimal(amt)
    for inv_id, d, amt in db.session.query(Withdrawal.investor_id, Withdrawal.value_date, Withdrawal.amount).filter(
            Withdrawal.status == WITHDRAWAL_APPROVED, Withdrawal.value_date <= through):
        events[d].append((inv_id, -Decimal(amt)))
        withdrawals_by_month[d.replace(day=1)] += Decimal(amt)
    if not events:
        return []
    interest = {p.period_start: Decimal(p.total_net) for p in InterestPeriod.query.filter(
        InterestPeriod.status.in_(LOCKED_PERIOD_STATUSES))}

    days = sorted(events)
    balances = defaultdict(Decimal)
    month = days[0].replace(day=1)
    out, i, prev = [], 0, None
    while month <= through:
        _, month_end = month_bounds(month.year, month.month)
        cutoff = min(month_end, through)
        while i < len(days) and days[i] <= cutoff:
            for inv_id, amt in events[days[i]]:
                balances[inv_id] += amt
            i += 1
        aum = sum(balances.values(), ZERO)
        change = aum - prev if prev is not None else None
        out.append({
            "month": month,
            "label": f"{month:%B %Y}" + (" (to date)" if cutoff < month_end else ""),
            "as_of": cutoff,
            "aum": aum,
            "change": change,
            "change_pct": (change / prev) if (change is not None and prev) else None,
            "deposits": deposits_by_month.get(month, ZERO),
            "withdrawals": withdrawals_by_month.get(month, ZERO),
            "interest": interest.get(month),
            "investors": sum(1 for b in balances.values() if b > 0),
        })
        prev = aum
        month = _add_months(month, 1)
    return out


def aum_workbook(through: date | None = None) -> tuple[bytes, list[dict]]:
    series = aum_series(through)
    rows = [[r["label"], r["as_of"], r["aum"], r["change"], r["change_pct"], r["deposits"], r["withdrawals"],
             r["interest"], r["investors"]] for r in series]
    cols = [Col("Month", 22), Col("Balance date", 14, "date"), Col("Funds under management (KES)", 28, "money"),
            Col("Change on prior month (KES)", 26, "money"), Col("Change (%)", 12, "percent"),
            Col("Deposits (KES)", 18, "money"), Col("Withdrawals (KES)", 18, "money"),
            Col("Interest for month (KES)", 22, "money"), Col("Investors with a balance", 22, "int")]
    latest = series[-1] if series else None
    info = [f"Funds under management at {latest['as_of']:%d %b %Y}: KES {latest['aum']:,.2f}" if latest
            else "No deposits recorded yet.",
            "Month-end balances (deposits posted less withdrawals approved). Interest shows once a month is approved.",
            _stamp()]
    return build_workbook("Portfolio summary (AUM)", info, cols, rows, None, "AUM"), series


def aum_report(args) -> Report:
    data, series = aum_workbook()
    desc = f"{series[0]['label']} to {series[-1]['label']}" if series else "no data"
    return Report(f"Anchorstone_AUM_summary_{today_eat()}.xlsx", data, desc, len(series))


# 6 ── Audit log ───────────────────────────────────────────────────────────


def audit_report(args) -> Report:
    from app.Audit.route import filtered_audit_logs

    start, end = _range(args)
    q = filtered_audit_logs(args)
    rows = [[r.timestamp, r.user_name, r.user_email, r.action, r.target_type, r.target_name, r.description,
             "OK" if r.success else "Failed", r.ip_address] for r in q.limit(MAX_ROWS)]
    cols = [Col("When", 18, "datetime"), Col("User", 22), Col("User email", 30), Col("Action", 26),
            Col("Target type", 16), Col("Target", 22), Col("Details", 60), Col("Result", 9), Col("IP address", 16)]
    parts = [fmt_range(start, end)]
    if args.get("user"):
        parts.append(f"user contains “{args['user']}”")
    if args.get("action"):
        parts.append(f"action {args['action']}")
    desc = " · ".join(parts)
    data = build_workbook("Audit log", [desc, _stamp()], cols, rows, None, "Audit log")
    return Report(f"Anchorstone_audit_log{_suffix(start, end)}.xlsx", data, desc, len(rows))


# 7 ── Email log ───────────────────────────────────────────────────────────


def email_report(args) -> Report:
    start, end = _range(args)
    q = OutboxEmail.query.order_by(OutboxEmail.queued_at.desc(), OutboxEmail.id.desc())
    if start:
        q = q.filter(OutboxEmail.queued_at >= datetime.combine(start, time.min, EAT))
    if end:
        q = q.filter(OutboxEmail.queued_at < datetime.combine(end + timedelta(days=1), time.min, EAT))
    if args.get("status"):
        q = q.filter(OutboxEmail.status == args["status"])
    if args.get("type"):
        q = q.filter(OutboxEmail.email_type == args["type"])
    rows = []
    for e in q.limit(MAX_ROWS):
        code, name = _name(e.investor)
        status = EMAIL_STATUS_LABELS.get(e.status, e.status)
        if e.status == "cancelled" and e.decided_by:
            status = "Suppressed"
        rows.append([e.queued_at, code, name or e.recipient_name, e.recipient_email,
                     EMAIL_TYPE_LABELS.get(e.email_type, e.email_type), e.subject, status, e.sent_at,
                     e.decided_by, e.created_by, e.last_error if e.status == "failed" else None])
    cols = [Col("Created", 18, "datetime"), Col("Client code", 14), Col("Investor / recipient", 28),
            Col("Email address", 34), Col("Type", 22), Col("Subject", 44), Col("Status", 20),
            Col("Sent at", 18, "datetime"), Col("Confirmed / suppressed by", 28), Col("Created by", 28),
            Col("Error", 40)]
    desc = fmt_range(start, end) + (f" · status {args['status']}" if args.get("status") else "")
    data = build_workbook("Email log", [desc, _stamp()], cols, rows, None, "Emails")
    return Report(f"Anchorstone_email_log{_suffix(start, end)}.xlsx", data, desc, len(rows))


# name -> (builder, minimum role, title)
REPORTS = {
    "investors": (investors_report, "user", "Investors report"),
    "deposits": (deposits_report, "user", "Deposits report"),
    "withdrawals": (withdrawals_report, "user", "Withdrawals report"),
    "interest": (interest_report, "user", "Interest payout report"),
    "aum": (aum_report, "user", "Portfolio / AUM summary"),
    "audit-log": (audit_report, "admin", "Audit log export"),
    "email-log": (email_report, "admin", "Email log export"),
}
