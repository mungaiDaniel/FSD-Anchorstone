"""
Sends queued outbox emails over SMTP (Flask-Mail).

Attachments are sent exactly as stored with the email when it was created.

drain_queue() is called by the background scheduler every
EMAIL_QUEUE_INTERVAL_MINUTES (and by the "Send now" button). It claims rows
with a single UPDATE ... WHERE status='queued' ... RETURNING, so a second
scheduler process can never pick up — and double-send — the same email.
"""
import logging

from flask import current_app
from flask_mail import Mail, Message
from sqlalchemy import select

from app.database.database import db
from app.Emails.model import (
    EMAIL_INTEREST_STATEMENT,
    STATUS_FAILED,
    STATUS_QUEUED,
    STATUS_SENDING,
    STATUS_SENT,
    OutboxEmail,
)
from app.Interest.model import InterestPayout
from app.Settings import business as settings
from app.utils import brand
from app.utils.dates import utcnow
from app.utils.email_template import attach_brand_logo, get_email_title, render_branded_email_html

logger = logging.getLogger(__name__)

mail = Mail()


def _sender():
    address = current_app.config.get("MAIL_DEFAULT_SENDER") or current_app.config.get("MAIL_USERNAME")
    if not address:
        raise RuntimeError("No sender configured: set MAIL_DEFAULT_SENDER (or MAIL_USERNAME).")
    # A login without a password makes the mail server answer "530 Authentication
    # Required", which reads like a server fault. Say what's actually missing.
    if (current_app.config.get("MAIL_USERNAME") and not current_app.config.get("MAIL_PASSWORD")
            and not current_app.config.get("MAIL_SUPPRESS_SEND")):
        raise RuntimeError(
            "No email password is saved. Enter it in Settings -> Email sending and click Save "
            "(for Gmail, use an App password)."
        )
    return (brand.COMPANY_NAME, address)


def build_message(subject: str, body: str, recipient: str, email_type: str | None = None) -> Message:
    has_logo = brand.logo_path() is not None
    bcc = current_app.config.get("MAIL_BCC")
    msg = Message(
        subject=subject,
        recipients=[recipient],
        bcc=[bcc] if bcc else None,
        body=body,
        html=render_branded_email_html(get_email_title(email_type), body, has_logo=has_logo),
        sender=_sender(),
    )
    if has_logo:
        attach_brand_logo(msg)
    return msg


def _send_one(email: OutboxEmail) -> None:
    msg = build_message(email.subject, email.body, email.recipient_email, email.email_type)
    if email.attachment is not None:
        # Generated and stored when the email was created; never rebuilt here.
        msg.attach(email.attachment.filename, email.attachment.content_type, email.attachment.data)
    elif email.email_type == EMAIL_INTEREST_STATEMENT and email.payout_id:
        # Only interest statements approved before PDFs were stored at approval.
        from app.utils.pdf_generator import generate_interest_statement_pdf, interest_statement_filename

        payout = db.session.get(InterestPayout, email.payout_id)
        msg.attach(interest_statement_filename(payout), "application/pdf",
                   generate_interest_statement_pdf(email.payout_id))
    mail.send(msg)


def send_outbox_email(email_id: int) -> bool:
    email = db.session.get(OutboxEmail, email_id)
    if email is None:
        return False
    email.attempts += 1
    try:
        _send_one(email)
    except Exception as e:  # SMTP / PDF errors are recorded on the row, not raised
        logger.warning("Email %s failed (attempt %s): %s", email_id, email.attempts, e)
        email.last_error = str(e)[:2000]
        email.status = STATUS_QUEUED if email.attempts < settings.get("email.max_attempts") else STATUS_FAILED
        db.session.commit()
        return False
    email.status = STATUS_SENT
    email.sent_at = utcnow()
    email.last_error = None
    db.session.commit()
    return True


def drain_queue(batch_size: int = 100) -> dict:
    subq = (
        select(OutboxEmail.id)
        .where(OutboxEmail.status == STATUS_QUEUED)
        .order_by(OutboxEmail.queued_at.asc(), OutboxEmail.id.asc())
        .limit(batch_size)
        .with_for_update(skip_locked=True)
    )
    claim = (
        OutboxEmail.__table__.update()
        .where(OutboxEmail.id.in_(subq))
        .values(status=STATUS_SENDING)
        .returning(OutboxEmail.id)
    )
    ids = [row[0] for row in db.session.execute(claim)]
    db.session.commit()

    sent = failed = 0
    for email_id in ids:
        try:
            ok = send_outbox_email(email_id)
        except Exception:
            logger.error("Unexpected error sending email %s", email_id, exc_info=True)
            db.session.rollback()
            stuck = db.session.get(OutboxEmail, email_id)
            if stuck is not None and stuck.status == STATUS_SENDING:
                stuck.status = STATUS_FAILED
                db.session.commit()
            ok = False
        sent += ok
        failed += not ok
    if ids:
        logger.info("Email queue: %s sent, %s not sent", sent, failed)
    return {"claimed": len(ids), "sent": sent, "failed": failed}


def recover_stuck_sending() -> int:
    """Rows left in 'sending' by a crash/restart go back to the queue."""
    count = (
        db.session.query(OutboxEmail)
        .filter(OutboxEmail.status == STATUS_SENDING)
        .update({"status": STATUS_QUEUED})
    )
    db.session.commit()
    return count
