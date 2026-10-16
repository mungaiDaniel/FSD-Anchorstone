from datetime import datetime, timezone
from sqlalchemy import Boolean, CheckConstraint, Column, Date, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
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


class SettingVersion(Base, db.Model):
    """
    One immutable, effective-dated value of a business-rule setting
    (app/Settings/registry.py). A change is a new row, made through a change
    request; the database refuses UPDATE and DELETE.
    """

    __tablename__ = "setting_versions"
    __table_args__ = (
        CheckConstraint("scope_type IN ('global', 'branch', 'product')", name="ck_setting_versions_scope_type"),
        CheckConstraint("(scope_type = 'global') = (scope_id IS NULL)", name="ck_setting_versions_scope_id"),
        CheckConstraint("source IN ('working_assumption', 'client_confirmed', 'internal_decision')",
                        name="ck_setting_versions_source"),
        CheckConstraint("lower(approved_by) <> lower(created_by)", name="ck_setting_versions_maker_not_checker"),
        Index("uq_setting_versions_key_scope_date", "key", "scope_type", text("coalesce(scope_id, 0)"),
              "effective_from", unique=True),
        Index("ix_setting_versions_lookup", "key", "scope_type", "scope_id", "effective_from"),
    )

    id = Column(Integer, primary_key=True)
    key = Column(String(80), nullable=False)
    scope_type = Column(String(10), nullable=False, default="global", server_default="global")
    scope_id = Column(Integer, nullable=True)
    value = Column(JSONB, nullable=False)
    effective_from = Column(Date, nullable=False)
    version_no = Column(Integer, nullable=False)
    source = Column(String(20), nullable=False)
    evidence = Column(Text, nullable=True)  # WA ref, questionnaire answer, document id or meeting note
    reason = Column(Text, nullable=True)
    change_request_id = Column(Integer, ForeignKey("change_requests.id", ondelete="RESTRICT"), nullable=True)
    created_by = Column(String(120), nullable=False)
    approved_by = Column(String(120), nullable=False)
    approved_at = Column(DateTime(timezone=True), nullable=False)

    def to_dict(self) -> dict:
        return {"id": self.id, "key": self.key, "scope_type": self.scope_type, "scope_id": self.scope_id,
                "value": self.value, "effective_from": self.effective_from.isoformat(),
                "version_no": self.version_no, "source": self.source, "evidence": self.evidence,
                "reason": self.reason, "change_request_id": self.change_request_id,
                "created_by": self.created_by, "approved_by": self.approved_by,
                "approved_at": self.approved_at.isoformat() if self.approved_at else None}
