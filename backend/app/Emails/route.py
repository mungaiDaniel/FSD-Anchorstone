from flask import Blueprint, current_app, make_response, request
from sqlalchemy import func, or_

from app.auth import actor_email, requires
from app.database.database import db
from app.Emails.model import (
    STATUS_CANCELLED,
    STATUS_FAILED,
    STATUS_QUEUED,
    OutboxEmail,
)
from app.Emails import statements
from app.Emails.sender import drain_queue
from app.logic.scheduler import EMAIL_JOB_ID, next_run
from app.utils.audit_log import create_audit_log
from app.utils.dates import utcnow
from app.utils.http import Conflict, NotFound, ok, page_args, paginate

emails_v1 = Blueprint("emails_v1", __name__)


@emails_v1.get("/api/v1/emails")
@requires("email.view")
def list_emails():
    page, per_page = page_args(request.args)
    q = OutboxEmail.query
    if request.args.get("status"):
        q = q.filter(OutboxEmail.status == request.args["status"])
    if request.args.get("type"):
        q = q.filter(OutboxEmail.email_type == request.args["type"])
    term = (request.args.get("search") or "").strip()
    if term:
        like = f"%{term}%"
        q = q.filter(or_(OutboxEmail.recipient_email.ilike(like), OutboxEmail.recipient_name.ilike(like),
                         OutboxEmail.subject.ilike(like)))
    q = q.order_by(OutboxEmail.queued_at.desc(), OutboxEmail.id.desc())
    return ok(paginate(q, page, per_page, lambda e: e.to_dict()))


@emails_v1.get("/api/v1/emails/status")
@requires("email.view")
def queue_status():
    counts = dict(db.session.query(OutboxEmail.status, func.count()).group_by(OutboxEmail.status).all())
    return ok({
        "counts": counts,
        "next_run_at": next_run(EMAIL_JOB_ID),
        "suppressed": bool(current_app.config.get("MAIL_SUPPRESS_SEND")),
    })


def _get(email_id: int) -> OutboxEmail:
    email = db.session.get(OutboxEmail, email_id)
    if email is None:
        raise NotFound("Email not found.")
    return email


@emails_v1.post("/api/v1/emails/<int:email_id>/retry")
@requires("email.manage")
def retry(email_id):
    email = _get(email_id)
    if email.status not in (STATUS_FAILED, STATUS_CANCELLED):
        raise Conflict("Only failed or cancelled emails can be retried.")
    statements.retry_allowed(email)
    email.status = STATUS_QUEUED
    email.attempts = 0
    email.queued_at = utcnow()
    create_audit_log("RETRY_EMAIL", target_type="email", target_id=email.id, target_name=email.recipient_email)
    db.session.commit()
    return ok(email.to_dict(), "Email re-queued.")


@emails_v1.post("/api/v1/emails/<int:email_id>/cancel")
@requires("email.manage")
def cancel(email_id):
    email = _get(email_id)
    if email.status != STATUS_QUEUED:
        raise Conflict("Only queued emails can be cancelled.")
    email.status = STATUS_CANCELLED
    create_audit_log("CANCEL_EMAIL", target_type="email", target_id=email.id, target_name=email.recipient_email)
    db.session.commit()
    return ok(email.to_dict(), "Email cancelled.")


@emails_v1.post("/api/v1/emails/send-now")
@requires("email.send_now")
def send_now():
    result = drain_queue(batch_size=100)
    return ok(result, f"{result['sent']} sent, {result['failed']} not sent.")



# ── On-demand statements: generate, then confirm or suppress (admins only) ──


@emails_v1.post("/api/v1/investors/<int:investor_id>/statement-email")
@requires("statement.generate")
def generate_statement_email(investor_id):
    email = statements.generate_for_investor(investor_id, actor_email())
    return ok(email.to_dict(), "Statement generated. Confirm it on the Emails page to send it.", 201)


@emails_v1.post("/api/v1/emails/statements/bulk")
@requires("statement.generate")
def generate_statement_emails_bulk():
    result = statements.generate_bulk(request.get_json(silent=True) or {}, actor_email())
    if result["duplicate"]:
        return ok(result, "These statements were already generated; nothing new was added.")
    msg = f"{result['generated']} statement(s) generated and waiting for confirmation."
    if result["skipped_pending"]:
        msg += f" {result['skipped_pending']} skipped: already waiting for confirmation."
    return ok(result, msg, 201)


@emails_v1.post("/api/v1/emails/confirm")
@requires("email.confirm")
def confirm_emails():
    result = statements.confirm_or_suppress(request.get_json(silent=True) or {}, True, actor_email())
    return ok(result, f"{result['changed']} email(s) confirmed and queued to send.")


@emails_v1.post("/api/v1/emails/suppress")
@requires("email.confirm")
def suppress_emails():
    result = statements.confirm_or_suppress(request.get_json(silent=True) or {}, False, actor_email())
    return ok(result, f"{result['changed']} email(s) suppressed. They won't be sent.")


@emails_v1.get("/api/v1/emails/<int:email_id>/attachment")
@requires("email.view")
def email_attachment(email_id):
    email = _get(email_id)
    if email.attachment is None:
        raise NotFound("This email has no stored attachment.")
    response = make_response(email.attachment.data)
    response.headers["Content-Type"] = email.attachment.content_type
    response.headers["Content-Disposition"] = f'inline; filename="{email.attachment.filename}"'
    return response
