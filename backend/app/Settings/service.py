"""
Applies DB-backed EmailSettings on top of config.py/.env, and — critically —
refreshes Flask-Mail's cached SMTP connection state whenever they change.

Flask-Mail captures MAIL_* config once, in Mail.init_app(), into
app.extensions["mail"]; Mail.connect() reads that cached state, not
current_app.config, on every send. So just updating app.config after startup
would silently do nothing to actual mail delivery — this module is what makes
"change the SMTP account in Settings" take effect without a server restart:
it updates app.config AND re-runs mail.init_app(app) in the same step.
"""
import logging

from app.Settings.model import EmailSettings
from app.utils.crypto import decrypt_secret, encrypt_secret

logger = logging.getLogger(__name__)

MAIL_FIELD_MAP = {
    "mail_server": "MAIL_SERVER",
    "mail_port": "MAIL_PORT",
    "mail_use_tls": "MAIL_USE_TLS",
    "mail_use_ssl": "MAIL_USE_SSL",
    "mail_username": "MAIL_USERNAME",
    "mail_default_sender": "MAIL_DEFAULT_SENDER",
    "mail_bcc": "MAIL_BCC",
}

QUEUE_FIELD_MAP = {
    "email_queue_batch_size": "EMAIL_QUEUE_BATCH_SIZE",
    "email_queue_interval_minutes": "EMAIL_QUEUE_INTERVAL_MINUTES",
}

# The config.py/.env value for each key, captured once on first use — BEFORE any
# DB override has ever been applied. Without this, clearing a DB override back
# to "no override" would have nothing to fall back to but app.config, which by
# then already holds the (now-cleared) override, not the original value.
_pristine_config: dict = {}


def _capture_pristine(app) -> None:
    for config_key in list(MAIL_FIELD_MAP.values()) + list(QUEUE_FIELD_MAP.values()) + ["MAIL_PASSWORD"]:
        if config_key not in _pristine_config:
            _pristine_config[config_key] = app.config.get(config_key)


def get_effective_email_settings(app, session) -> dict:
    """
    Values the app is ACTUALLY using right now: the DB override where set,
    otherwise the original config.py/.env value. Password is never included
    here — callers that need it for sending use _effective_mail_password.
    """
    _capture_pristine(app)
    row = EmailSettings.get_singleton(session)
    effective = {}
    for db_field, config_key in MAIL_FIELD_MAP.items():
        db_value = getattr(row, db_field)
        effective[db_field] = db_value if db_value is not None else _pristine_config.get(config_key)
    effective["has_password"] = bool(row.mail_password_encrypted) or bool(_pristine_config.get("MAIL_PASSWORD"))
    for db_field, config_key in QUEUE_FIELD_MAP.items():
        db_value = getattr(row, db_field)
        effective[db_field] = db_value if db_value is not None else _pristine_config.get(config_key)
    return effective


def _effective_mail_password(app, session) -> str:
    _capture_pristine(app)
    row = EmailSettings.get_singleton(session)
    if row.mail_password_encrypted:
        return decrypt_secret(row.mail_password_encrypted, app.config["SECRET_KEY"])
    return _pristine_config.get("MAIL_PASSWORD") or ""


def apply_email_settings_to_app(app, session) -> None:
    """Push the effective MAIL_* values onto app.config (falling back to the
    original config.py/.env value, not skipping, when a field's DB override has
    been cleared) and refresh Flask-Mail's cached connection state so the very
    next send uses them. Call this once at startup (after config.py loads,
    before EmailService.init_app) and again every time the Settings -> Email
    Sending form is saved."""
    from app.Emails.sender import mail

    _capture_pristine(app)
    row = EmailSettings.get_singleton(session)
    for db_field, config_key in MAIL_FIELD_MAP.items():
        db_value = getattr(row, db_field)
        app.config[config_key] = db_value if db_value is not None else _pristine_config.get(config_key)

    app.config["MAIL_PASSWORD"] = _effective_mail_password(app, session)

    mail.init_app(app)
    logger.info("Applied email settings to app config and refreshed Flask-Mail connection state.")


def save_email_settings(app, session, data: dict, updated_by: str = None) -> EmailSettings:
    """
    Upserts the singleton EmailSettings row from a PATCH payload, then applies
    it immediately (see apply_email_settings_to_app). `password` is only
    written (and re-encrypted) when a non-empty value is supplied — omitting
    it or sending an empty string keeps whatever password is already saved.
    """
    row = EmailSettings.get_singleton(session)

    simple_fields = ["mail_server", "mail_username", "mail_default_sender", "mail_bcc"]
    for field in simple_fields:
        if field in data:
            value = data[field]
            setattr(row, field, (value.strip() or None) if isinstance(value, str) else value)

    if "mail_port" in data and data["mail_port"] is not None:
        row.mail_port = int(data["mail_port"])
    if "mail_use_tls" in data:
        row.mail_use_tls = bool(data["mail_use_tls"])
    if "mail_use_ssl" in data:
        row.mail_use_ssl = bool(data["mail_use_ssl"])

    password = data.get("mail_password")
    if isinstance(password, str) and password.strip():
        row.mail_password_encrypted = encrypt_secret(password.strip(), app.config["SECRET_KEY"])

    row.updated_by = updated_by
    session.add(row)
    session.commit()

    apply_email_settings_to_app(app, session)
    return row


def save_email_queue_settings(app, session, batch_size: int, interval_minutes: int, updated_by: str = None) -> EmailSettings:
    row = EmailSettings.get_singleton(session)
    row.email_queue_batch_size = batch_size
    row.email_queue_interval_minutes = interval_minutes
    row.updated_by = updated_by
    session.add(row)
    session.commit()

    from app.logic.scheduler import reschedule_email_queue
    reschedule_email_queue(interval_minutes)  # batch size is read fresh on every run
    return row
