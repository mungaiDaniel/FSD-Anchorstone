"""
Monthly AUM summary email: the AUM spreadsheet (report #5) emailed to a
configured list of internal recipients.

It goes through the normal email outbox, held as "Awaiting confirmation": an
admin confirms (sends) or suppresses it on the Emails page, as with on-demand
statements. It is not tied to an investor.
"""
import re
from datetime import date, timedelta

from app.database.database import db
from app.Emails.model import EMAIL_AUM_REPORT, STATUS_PENDING, EmailAttachment, OutboxEmail
from app.Reports.excel import XLSX_MIME
from app.Reports.model import ReportSchedule
from app.Reports.reports import aum_workbook
from app.utils.audit_log import create_audit_log
from app.utils.dates import today_eat, utcnow
from app.utils.http import ValidationError
from app.utils.money import fmt_kes

MAX_RECIPIENTS = 20
EMAIL_RE = re.compile(r"^[^@\s,]+@[^@\s,]+\.[^@\s,]+$")


def parse_recipients(value) -> list[str]:
    if isinstance(value, str):
        value = re.split(r"[,\s;]+", value)
    if not isinstance(value, list):
        raise ValidationError("recipients must be a list of email addresses.")
    out = []
    for raw in value:
        email = str(raw).strip().lower()
        if not email:
            continue
        if not EMAIL_RE.match(email):
            raise ValidationError(f"“{email}” is not a valid email address.")
        if email not in out:
            out.append(email)
    if len(out) > MAX_RECIPIENTS:
        raise ValidationError(f"At most {MAX_RECIPIENTS} recipients.")
    return out


def save_schedule(data: dict, actor: str) -> ReportSchedule:
    row = ReportSchedule.get(db.session, lock=True)
    old = row.to_dict()
    if "aum_recipients" in data:
        row.aum_recipients = ", ".join(parse_recipients(data["aum_recipients"])) or None
    if "aum_enabled" in data:
        row.aum_enabled = bool(data["aum_enabled"])
    if row.aum_enabled and not row.recipients:
        raise ValidationError("Add at least one recipient before turning the schedule on.")
    row.updated_by = actor
    db.session.commit()
    create_audit_log("UPDATE_REPORT_SCHEDULE", target_type="report_schedule", target_name="Monthly AUM summary",
                     old_value=old, new_value=row.to_dict())
    return row


def _last_completed_month(today: date) -> date:
    return (today.replace(day=1) - timedelta(days=1)).replace(day=1)


def generate_aum_emails(recipients: list[str], month: date, actor: str) -> list[OutboxEmail]:
    """Pending emails (one per recipient) with the AUM spreadsheet up to the end
    of `month` attached. Caller commits."""
    from app.utils.dates import month_bounds

    _, month_end = month_bounds(month.year, month.month)
    data, series = aum_workbook(through=min(month_end, today_eat()))
    latest = series[-1] if series else None
    label = f"{month:%B %Y}"
    lines = []
    if latest:
        lines.append(f"• Funds under management at {latest['as_of']:%d %B %Y}: {fmt_kes(latest['aum'])}")
        if latest["change"] is not None:
            sign = "+" if latest["change"] >= 0 else "−"
            pct = f" ({sign}{abs(latest['change_pct']) * 100:.2f}%)" if latest["change_pct"] is not None else ""
            lines.append(f"• Change on the previous month: {sign}{fmt_kes(abs(latest['change']))}{pct}")
        lines.append(f"• Deposits in {label}: {fmt_kes(latest['deposits'])}")
        lines.append(f"• Withdrawals in {label}: {fmt_kes(latest['withdrawals'])}")
        lines.append(f"• Interest for {label}: "
                     + (fmt_kes(latest["interest"]) if latest["interest"] is not None else "not yet approved"))
        lines.append(f"• Investors with a balance: {latest['investors']}")
    else:
        lines.append("• No deposits have been recorded yet.")
    body = (
        "Hello,\n\n"
        f"Here is the monthly funds-under-management summary for {label}.\n\n"
        "SUMMARY\n\n" + "\n".join(lines) + "\n\n"
        "The attached spreadsheet shows every month since the first deposit.\n\n"
        "Anchorstone Capital Ltd — Investor Statement System"
    )
    emails = []
    for to in recipients:
        email = OutboxEmail(
            email_type=EMAIL_AUM_REPORT,
            investor_id=None,
            recipient_email=to,
            recipient_name=None,
            subject=f"Monthly AUM summary — {label}",
            body=body,
            status=STATUS_PENDING,
            created_by=actor,
        )
        email.attachment = EmailAttachment(filename=f"Anchorstone_AUM_summary_{month:%Y-%m}.xlsx",
                                           content_type=XLSX_MIME, data=data)
        db.session.add(email)
        emails.append(email)
    return emails


def run_now(actor: str) -> list[OutboxEmail]:
    """Super admin "Generate now": the last completed month, to the saved recipients."""
    row = ReportSchedule.get(db.session)
    if not row.recipients:
        raise ValidationError("Add at least one recipient first.")
    month = _last_completed_month(today_eat())
    emails = generate_aum_emails(row.recipients, month, actor)
    db.session.commit()
    create_audit_log("GENERATE_AUM_REPORT", target_type="report_schedule", target_name=f"{month:%B %Y}",
                     description=f"Generated on request for {len(emails)} recipient(s), awaiting confirmation")
    return emails


def scheduled_run(today: date | None = None) -> int:
    """Called by the scheduler on the 1st. Generates last month's summary once."""
    today = today or today_eat()
    row = ReportSchedule.get(db.session, lock=True)
    month = _last_completed_month(today)
    if not row.aum_enabled or not row.recipients or row.aum_last_month == f"{month:%Y-%m}":
        db.session.commit()
        return 0
    emails = generate_aum_emails(row.recipients, month, "scheduler")
    row.aum_last_month = f"{month:%Y-%m}"
    row.aum_last_run_at = utcnow()
    db.session.commit()
    create_audit_log("GENERATE_AUM_REPORT", target_type="report_schedule", target_name=f"{month:%B %Y}",
                     description=f"Scheduled run for {len(emails)} recipient(s), awaiting confirmation",
                     actor_user_email="scheduler", actor_user_name="Scheduler")
    return len(emails)
