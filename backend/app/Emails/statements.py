"""
On-demand account statements ("as of today"), for one investor or many.

Each statement is generated straight away (PDF + email text, frozen at that
moment) and lands in the email outbox as PENDING. Nothing is sent until an
admin confirms it; an admin can instead suppress it. The background sender
only ever picks up QUEUED emails, so a pending statement can't slip out.

  generate  ->  pending  --confirm-->  queued  -> sending -> sent
                         --suppress->  cancelled
"""
from flask import current_app

from app.database.database import db
from app.Emails.model import (
    EMAIL_ACCOUNT_STATEMENT,
    EMAIL_AUM_REPORT,
    STATUS_CANCELLED,
    STATUS_PENDING,
    STATUS_QUEUED,
    EmailAttachment,
    OutboxEmail,
)
from app.Investors.model import Investor
from app.Investors.service import apply_investor_filters
from app.Transactions.ledger import investor_totals
from app.utils.audit_log import create_audit_log
from app.utils.dates import today_eat, utcnow
from app.utils.http import Conflict, NotFound, ValidationError
from app.utils.money import fmt_kes
from app.utils.pdf_generator import generate_account_statement_pdf

MAX_RECIPIENTS = 1_000
MAX_DECISIONS = 2_000


def _body(investor: Investor, as_of) -> str:
    t = investor_totals(investor.id)
    lines = [
        f"• Current balance: {fmt_kes(t['balance'])}",
        f"• Total deposited: {fmt_kes(t['total_deposited'])}",
        f"• Total withdrawn: {fmt_kes(t['total_withdrawn'])}",
        f"• Interest paid to date: {fmt_kes(t['interest_paid'])}",
    ]
    if t["interest_payable"] > 0:
        lines.append(f"• Interest due (approved, not yet paid): {fmt_kes(t['interest_payable'])}")
    company = current_app.config.get("COMPANY_NAME", "Anchorstone Capital Ltd")
    return (
        f"Dear {investor.full_name.split()[0]},\n\n"
        f"Please find attached your {company} account statement as of {as_of:%d %B %Y}.\n\n"
        "SUMMARY\n\n" + "\n".join(lines) + "\n\n"
        "The attached statement lists every deposit and withdrawal on your account, and your interest history.\n\n"
        "If anything in this statement doesn't match your records, please contact us right away.\n\n"
        f"Kind regards,\n{company}"
    )


def _has_pending(investor_id: int) -> bool:
    return db.session.query(OutboxEmail.id).filter(
        OutboxEmail.investor_id == investor_id,
        OutboxEmail.email_type == EMAIL_ACCOUNT_STATEMENT,
        OutboxEmail.status == STATUS_PENDING,
    ).first() is not None


def _create(investor: Investor, actor: str, send_key: str | None) -> OutboxEmail:
    as_of = today_eat()
    pdf = generate_account_statement_pdf(investor.id)
    email = OutboxEmail(
        email_type=EMAIL_ACCOUNT_STATEMENT,
        investor_id=investor.id,
        recipient_email=investor.email,
        recipient_name=investor.full_name,
        subject=f"Your account statement — {as_of:%d %B %Y}",
        body=_body(investor, as_of),
        status=STATUS_PENDING,
        created_by=actor,
        send_key=send_key,
    )
    email.attachment = EmailAttachment(
        filename=f"Anchorstone-statement-{investor.client_code}-{as_of:%Y-%m-%d}.pdf",
        content_type="application/pdf",
        data=pdf,
    )
    db.session.add(email)
    return email


# ── Generate ─────────────────────────────────────────────────────────────


def generate_for_investor(investor_id: int, actor: str) -> OutboxEmail:
    investor = db.session.get(Investor, investor_id)
    if investor is None:
        raise NotFound("Investor not found.")
    if _has_pending(investor.id):
        raise Conflict(
            "A statement for this investor is already waiting for confirmation on the Emails page. "
            "Confirm or suppress it first."
        )
    email = _create(investor, actor, None)
    db.session.flush()
    create_audit_log(
        "GENERATE_STATEMENT_EMAIL", target_type="investor", target_id=investor.id,
        target_name=investor.client_code, description="Statement as of today, awaiting confirmation",
        new_value={"email_id": email.id},
    )
    db.session.commit()
    return email


def resolve_recipients(selection) -> list[Investor]:
    """selection = {"investor_ids": [..]}  or  {"filter": {"search", "status"}, "exclude_ids": [..]}"""
    if not isinstance(selection, dict):
        raise ValidationError("recipients is required.")
    if "investor_ids" in selection:
        ids = selection.get("investor_ids")
        if not isinstance(ids, list) or not ids:
            raise ValidationError("Select at least one investor.")
        try:
            ids = sorted({int(i) for i in ids})
        except (TypeError, ValueError):
            raise ValidationError("investor_ids must be a list of investor ids.")
        investors = Investor.query.filter(Investor.id.in_(ids)).order_by(Investor.full_name).all()
        missing = set(ids) - {i.id for i in investors}
        if missing:
            raise NotFound(f"Investor(s) not found: {', '.join(map(str, sorted(missing)))}.")
    elif "filter" in selection:
        f = selection.get("filter") or {}
        if not isinstance(f, dict):
            raise ValidationError("filter must be an object with search and status.")
        q = apply_investor_filters(Investor.query, f.get("search"), f.get("status"))
        try:
            exclude = [int(i) for i in (selection.get("exclude_ids") or [])]
        except (TypeError, ValueError):
            raise ValidationError("exclude_ids must be a list of investor ids.")
        if exclude:
            q = q.filter(Investor.id.notin_(exclude))
        investors = q.order_by(Investor.full_name).all()
    else:
        raise ValidationError("recipients must give investor_ids or a filter.")
    if not investors:
        raise ValidationError("No investors match this selection.")
    if len(investors) > MAX_RECIPIENTS:
        raise ValidationError(f"Too many investors ({len(investors):,}); the limit is {MAX_RECIPIENTS:,} at a time.")
    return investors


def generate_bulk(data: dict, actor: str) -> dict:
    import uuid

    try:
        send_key = str(uuid.UUID(str(data.get("send_key") or "")))
    except ValueError:
        raise ValidationError("send_key must be a UUID generated by the page.")
    investors = resolve_recipients(data.get("recipients"))

    # The whole request runs in one transaction, so any row with this key means
    # it already went through (a double click or a retried request).
    if db.session.query(OutboxEmail.id).filter(OutboxEmail.send_key == send_key).first() is not None:
        return {"generated": 0, "skipped_pending": 0, "selected": len(investors), "duplicate": True}

    generated = skipped = 0
    for inv in investors:
        if _has_pending(inv.id):
            skipped += 1  # one waiting statement per investor; it's already on the Emails page
            continue
        _create(inv, actor, send_key)
        generated += 1

    create_audit_log(
        "BULK_GENERATE_STATEMENTS", target_type="statement_batch", target_name=send_key,
        description=f"{generated} statement(s) generated, awaiting confirmation"
                    + (f"; {skipped} skipped (already awaiting confirmation)" if skipped else ""),
        new_value={"generated": generated, "skipped_pending": skipped, "selected": len(investors),
                   "selection": (data.get("recipients") or {}).get("filter") or "selected investors",
                   "send_key": send_key},
    )
    db.session.commit()
    return {"generated": generated, "skipped_pending": skipped, "selected": len(investors), "duplicate": False}


# ── Confirm / suppress ───────────────────────────────────────────────────


def _ids(data: dict) -> list[int]:
    if data.get("all_pending") is True:
        ids = [r[0] for r in db.session.query(OutboxEmail.id).filter(OutboxEmail.status == STATUS_PENDING)]
        if not ids:
            raise ValidationError("There are no emails awaiting confirmation.")
        if len(ids) > MAX_DECISIONS:
            raise ValidationError(f"More than {MAX_DECISIONS:,} emails are waiting; select them in smaller groups.")
        return ids
    ids = data.get("ids")
    if not isinstance(ids, list) or not ids:
        raise ValidationError("ids must be a non-empty list of email ids.")
    if len(ids) > MAX_DECISIONS:
        raise ValidationError(f"At most {MAX_DECISIONS:,} emails at a time.")
    try:
        return sorted({int(i) for i in ids})
    except (TypeError, ValueError):
        raise ValidationError("ids must be a list of email ids.")


def decide(ids: list[int], confirm: bool, actor: str) -> dict:
    """Confirm (send) or suppress pending emails. Anything not pending is skipped."""
    emails = (
        db.session.query(OutboxEmail).filter(OutboxEmail.id.in_(ids)).with_for_update().all()
    )
    if len(emails) != len(ids):
        missing = set(ids) - {e.id for e in emails}
        raise NotFound(f"Email(s) not found: {', '.join(map(str, sorted(missing)))}.")
    now = utcnow()
    changed = [e for e in emails if e.status == STATUS_PENDING]
    for e in changed:
        e.status = STATUS_QUEUED if confirm else STATUS_CANCELLED
        e.decided_by = actor
        e.decided_at = now
        if confirm:
            e.queued_at = now
        else:
            e.last_error = "Suppressed by an admin; not sent."

    action = "CONFIRM_EMAIL" if confirm else "SUPPRESS_EMAIL"
    for e in changed:
        create_audit_log(
            action, target_type="investor" if e.investor_id else "email", target_id=e.investor_id or e.id,
            target_name=e.investor.client_code if e.investor else e.recipient_email,
            description=f"{e.subject} (to {e.recipient_email})", new_value={"email_id": e.id},
        )
    db.session.commit()
    return {"changed": len(changed), "skipped": len(emails) - len(changed),
            "emails": [e.to_dict() for e in changed]}


def confirm_or_suppress(data: dict, confirm: bool, actor: str) -> dict:
    return decide(_ids(data), confirm, actor)


def retry_allowed(email: OutboxEmail) -> None:
    if email.email_type in (EMAIL_ACCOUNT_STATEMENT, EMAIL_AUM_REPORT) and email.status == STATUS_CANCELLED:
        raise Conflict("A suppressed report or statement has out-of-date figures. Generate a new one instead.")
