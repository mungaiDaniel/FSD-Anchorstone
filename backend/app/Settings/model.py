from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from base_model import Base
from app.database.database import db


class EmailSettings(Base, db.Model):
    """
    Singleton row (id is always 1) overriding the MAIL_*/EMAIL_QUEUE_* values that
    otherwise come from config.py/.env. Any column left NULL means "fall back to
    the config.py/.env value" — so this table can exist with everything unset and
    change nothing, and an admin can override one field (e.g. just the queue batch
    size) without having to also supply SMTP credentials.

    mail_password is stored encrypted (see app/utils/crypto.py) — never returned to
    the frontend in plaintext once saved.
    """
    __tablename__ = "email_settings"

    id = Column(Integer, primary_key=True)

    mail_server = Column(String(255), nullable=True)
    mail_port = Column(Integer, nullable=True)
    mail_use_tls = Column(Boolean, nullable=True)
    mail_use_ssl = Column(Boolean, nullable=True)
    mail_username = Column(String(255), nullable=True)
    mail_password_encrypted = Column(Text, nullable=True)
    mail_default_sender = Column(String(255), nullable=True)
    mail_bcc = Column(String(255), nullable=True)

    email_queue_batch_size = Column(Integer, nullable=True)
    email_queue_interval_minutes = Column(Integer, nullable=True)

    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    updated_by = Column(String(120), nullable=True)

    @classmethod
    def get_singleton(cls, session):
        row = session.query(cls).filter(cls.id == 1).first()
        if not row:
            row = cls(id=1)
            session.add(row)
            session.commit()
        return row
