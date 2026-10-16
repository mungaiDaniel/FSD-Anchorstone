"""
Outbox for every investor email. Replaces OFDS's separate pending_emails +
email_logs tables with one row per email that moves through:

    queued → sending → sent
                     ↘ failed (retried automatically up to the email.max_attempts setting, then
                               left for an admin to retry or cancel)
    queued → cancelled

Deposit and withdrawal confirmations are queued automatically, and so is a
reversal notice when a deposit whose confirmation was already sent is reversed. Interest
statements are queued when an admin approves the month's interest period.
The unique constraints guarantee no transaction or payout is emailed twice.
"""
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, LargeBinary, String, Text, UniqueConstraint, text

from app.database.database import db
from base_model import Base
from app.utils.dates import iso

EMAIL_DEPOSIT_CONFIRMATION = "DEPOSIT_CONFIRMATION"
EMAIL_WITHDRAWAL_CONFIRMATION = "WITHDRAWAL_CONFIRMATION"
# Sent when a deposit whose confirmation already went out is reversed.
EMAIL_DEPOSIT_REVERSAL = "DEPOSIT_REVERSAL"
EMAIL_INTEREST_STATEMENT = "INTEREST_STATEMENT"
# On-demand "as of today" statement an admin generates for one or many investors.
# Created as PENDING: an admin must confirm (send) or suppress it — see app/Emails/statements.py.
EMAIL_ACCOUNT_STATEMENT = "ACCOUNT_STATEMENT"
# Internal management email (not to an investor): monthly AUM summary — app/Reports/scheduled.py.
EMAIL_AUM_REPORT = "AUM_REPORT"
EMAIL_TYPES = (EMAIL_DEPOSIT_CONFIRMATION, EMAIL_DEPOSIT_REVERSAL, EMAIL_WITHDRAWAL_CONFIRMATION,
               EMAIL_INTEREST_STATEMENT, EMAIL_ACCOUNT_STATEMENT, EMAIL_AUM_REPORT)

STATUS_PENDING = "pending"      # awaiting an admin's confirm/suppress; never sent automatically
STATUS_QUEUED = "queued"
STATUS_SENDING = "sending"
STATUS_SENT = "sent"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"



def _utcnow():
    return datetime.now(timezone.utc)


class OutboxEmail(Base, db.Model):
    __tablename__ = "email_outbox"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'queued', 'sending', 'sent', 'failed', 'cancelled')", name="ck_email_outbox_status"
        ),
        UniqueConstraint("email_type", "deposit_id", name="uq_email_outbox_deposit"),
        UniqueConstraint("email_type", "withdrawal_id", name="uq_email_outbox_withdrawal"),
        UniqueConstraint("email_type", "payout_id", name="uq_email_outbox_payout"),
        # One email per investor per admin-triggered send: a resubmitted request
        # (double click, network retry) carries the same send_key and adds nothing.
        UniqueConstraint("send_key", "investor_id", name="uq_email_outbox_send_key_investor"),
        # A deposit reversal notice is sent at most once per deposit, and always names its deposit
        # (a NULL deposit_id would slip past any unique index).
        CheckConstraint("email_type <> 'DEPOSIT_REVERSAL' OR deposit_id IS NOT NULL",
                        name="ck_email_outbox_reversal_has_deposit"),
        Index("uq_email_outbox_deposit_reversal", "deposit_id", unique=True,
              postgresql_where=text("email_type = 'DEPOSIT_REVERSAL'")),
        Index("ix_email_outbox_status_queued_at", "status", "queued_at"),
    )

    id = Column(Integer, primary_key=True)
    email_type = Column(String(40), nullable=False, index=True)
    # NULL only for internal emails (the AUM summary); every investor email has one.
    investor_id = Column(Integer, ForeignKey("investors.id", ondelete="RESTRICT"), nullable=True, index=True)
    deposit_id = Column(Integer, ForeignKey("deposits.id", ondelete="RESTRICT"), nullable=True)
    withdrawal_id = Column(Integer, ForeignKey("withdrawals.id", ondelete="RESTRICT"), nullable=True)
    payout_id = Column(Integer, ForeignKey("interest_payouts.id", ondelete="RESTRICT"), nullable=True)

    recipient_email = Column(String(150), nullable=False)
    recipient_name = Column(String(150), nullable=True)
    subject = Column(String(255), nullable=False)
    body = Column(Text, nullable=False)  # plain text; rendered into the branded HTML template at send time

    # Set when an admin confirms or suppresses a pending email.
    decided_by = Column(String(120), nullable=True)
    decided_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(12), nullable=False, default=STATUS_QUEUED, server_default=STATUS_QUEUED)
    attempts = Column(Integer, nullable=False, default=0, server_default="0")
    last_error = Column(Text, nullable=True)
    queued_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    created_by = Column(String(120), nullable=True)
    # On-demand statements only: one UUID per request, shared by every investor in it.
    send_key = Column(String(36), nullable=True, index=True)

    investor = db.relationship("Investor")
    attachment = db.relationship("EmailAttachment", uselist=False, back_populates="email",
                                 cascade="all, delete-orphan")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "email_type": self.email_type,
            "investor_id": self.investor_id,
            "client_code": self.investor.client_code if self.investor else None,
            "deposit_id": self.deposit_id,
            "withdrawal_id": self.withdrawal_id,
            "payout_id": self.payout_id,
            "recipient_email": self.recipient_email,
            "recipient_name": self.recipient_name,
            "subject": self.subject,
            "body": self.body,
            "status": self.status,
            "attempts": self.attempts,
            "last_error": self.last_error,
            "queued_at": iso(self.queued_at),
            "sent_at": iso(self.sent_at),
            "created_by": self.created_by,
            "send_key": self.send_key,
            "decided_by": self.decided_by,
            "decided_at": iso(self.decided_at),
            "attachment_name": self.attachment.filename if self.attachment else None,
        }


class EmailAttachment(Base, db.Model):
    """A file stored with its email at the moment it was generated (on-demand
    statements), so what an admin reviews is exactly what the investor gets."""

    __tablename__ = "email_attachments"

    id = Column(Integer, primary_key=True)
    email_id = Column(Integer, ForeignKey("email_outbox.id", ondelete="CASCADE"), nullable=False, unique=True)
    filename = Column(String(200), nullable=False)
    content_type = Column(String(100), nullable=False, default="application/pdf")
    data = Column(LargeBinary, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    email = db.relationship("OutboxEmail", back_populates="attachment")
