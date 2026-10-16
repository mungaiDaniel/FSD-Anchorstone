"""
Settings -> Email Sending / Email Queue. Super admin only: these are SMTP
credentials and delivery-rate controls.
"""
from flask import Blueprint, current_app, request

from app.auth import actor_email, super_admin_required
from app.database.database import db
from app.Emails.sender import build_message, mail
from app.logic.scheduler import EMAIL_JOB_ID, next_run
from app.Settings.service import get_effective_email_settings, save_email_queue_settings, save_email_settings
from app.utils.audit_log import create_audit_log
from app.utils.http import ValidationError, ok

settings_v1 = Blueprint("settings_v1", __name__)


@settings_v1.get("/api/v1/settings/email")
@super_admin_required
def get_email_settings():
    return ok(get_effective_email_settings(current_app, db.session))


@settings_v1.patch("/api/v1/settings/email")
@super_admin_required
def patch_email_settings():
    data = request.get_json(silent=True) or {}
    if data.get("mail_port") is not None:
        try:
            port = int(data["mail_port"])
        except (TypeError, ValueError):
            raise ValidationError("mail_port must be a number.")
        if not 1 <= port <= 65535:
            raise ValidationError("mail_port must be between 1 and 65535.")
    save_email_settings(current_app, db.session, data, updated_by=actor_email())
    create_audit_log("UPDATE_EMAIL_SETTINGS", target_type="settings",
                     new_value={k: v for k, v in data.items() if k != "mail_password"})
    return ok(get_effective_email_settings(current_app, db.session), "Email settings saved and applied.")


@settings_v1.post("/api/v1/settings/email/test")
@super_admin_required
def send_test_email():
    recipient = str((request.get_json(silent=True) or {}).get("recipient") or "").strip()
    if not recipient:
        raise ValidationError("recipient is required.")
    body = (
        "This is a test email from the Anchorstone Capital Ltd statement system.\n\n"
        f"Sent by: {actor_email()}\n\n"
        "If you received this, your SMTP settings are working."
    )
    try:
        mail.send(build_message("Anchorstone test email", body, recipient, "TEST"))
    except Exception as e:
        raise ValidationError(f"Send failed: {e}")
    suppressed = bool(current_app.config.get("MAIL_SUPPRESS_SEND"))
    message = ("MAIL_SUPPRESS_SEND is on — nothing was actually sent." if suppressed
               else f"Test email sent to {recipient}.")
    return ok({"suppressed": suppressed}, message)


@settings_v1.get("/api/v1/settings/email-queue")
@super_admin_required
def get_queue_settings():
    effective = get_effective_email_settings(current_app, db.session)
    return ok({
        "batch_size": effective.get("email_queue_batch_size"),
        "interval_minutes": effective.get("email_queue_interval_minutes"),
        "next_run_at": next_run(EMAIL_JOB_ID),
    })


@settings_v1.patch("/api/v1/settings/email-queue")
@super_admin_required
def patch_queue_settings():
    data = request.get_json(silent=True) or {}
    try:
        batch_size, interval = int(data.get("batch_size")), int(data.get("interval_minutes"))
    except (TypeError, ValueError):
        raise ValidationError("batch_size and interval_minutes are required numbers.")
    if not 1 <= batch_size <= 1000:
        raise ValidationError("batch_size must be between 1 and 1000.")
    if not 1 <= interval <= 1440:
        raise ValidationError("interval_minutes must be between 1 and 1440.")
    save_email_queue_settings(current_app, db.session, batch_size, interval, updated_by=actor_email())
    create_audit_log("UPDATE_EMAIL_QUEUE", target_type="settings",
                     new_value={"batch_size": batch_size, "interval_minutes": interval})
    return ok(message=f"Email queue updated: up to {batch_size} emails every {interval} minute(s).")
