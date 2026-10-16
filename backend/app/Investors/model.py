from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, Sequence, String, Text, UniqueConstraint, text,
)

from app.Branches.model import HEAD_OFFICE_ID
from app.database.database import db
from base_model import Base

INVESTOR_STATUSES = ("active", "closed")
PAYOUT_METHODS = ("bank", "mpesa")

# Drives client codes (ACL-000001, ACL-000002, ...). A sequence rather than the
# primary key so the code is known before the row is inserted.
client_code_seq = Sequence("investor_client_code_seq", metadata=db.metadata)


class Investor(Base, db.Model):
    """One investor = one running deposit account (balance = deposits − withdrawals)."""

    __tablename__ = "investors"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'closed')", name="ck_investors_status"),
        CheckConstraint("payout_method IS NULL OR payout_method IN ('bank', 'mpesa')", name="ck_investors_payout_method"),
        # One account per person: email is the identity for statements.
        Index("uq_investors_email_lower", text("lower(email)"), unique=True),
        UniqueConstraint("party_id", name="uq_investors_party_id"),
        UniqueConstraint("account_id", name="uq_investors_account_id"),
    )

    id = Column(Integer, primary_key=True)
    client_code = Column(String(20), nullable=False, unique=True)
    full_name = Column(String(150), nullable=False)
    email = Column(String(150), nullable=False)
    phone = Column(String(30), nullable=True)
    id_number = Column(String(50), nullable=True)
    kra_pin = Column(String(20), nullable=True)

    # Where interest payouts and withdrawals are paid.
    payout_method = Column(String(10), nullable=True)
    bank_name = Column(String(100), nullable=True)
    payout_account = Column(String(100), nullable=True)  # bank account no. or M-Pesa number

    status = Column(String(10), nullable=False, default="active", server_default="active")
    branch_id = Column(Integer, ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False, index=True,
                       default=HEAD_OFFICE_ID, server_default=str(HEAD_OFFICE_ID))
    notes = Column(Text, nullable=True)
    # The investor's party and investment account (phase 2b). The name, phone, ID, PIN and payout
    # columns above mirror the party, kept in step by the service, so statements and reports read
    # them unchanged; email stays here for good as the statement address (one investor per email).
    party_id = Column(Integer, ForeignKey("parties.id", ondelete="RESTRICT", name="fk_investors_party_id"), nullable=False)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="RESTRICT", name="fk_investors_account_id"),
                        nullable=False)

    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    created_by = Column(String(120), nullable=False)
    closed_at = Column(DateTime(timezone=True), nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "client_code": self.client_code,
            "full_name": self.full_name,
            "email": self.email,
            "phone": self.phone,
            "id_number": self.id_number,
            "kra_pin": self.kra_pin,
            "payout_method": self.payout_method,
            "bank_name": self.bank_name,
            "payout_account": self.payout_account,
            "status": self.status,
            "branch_id": self.branch_id,
            "notes": self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "created_by": self.created_by,
            "closed_at": self.closed_at.isoformat() if self.closed_at else None,
        }
