"""
Deposits and withdrawals — the only two things that move an investor's balance.

    balance(as of D) = Σ posted deposits with value_date ≤ D
                     − Σ approved withdrawals with value_date ≤ D

Interest never touches the balance (it's paid out, see app/Interest). Rows are
never edited or deleted: a mistaken deposit is reversed (status → reversed,
with a reason), and a withdrawal only counts once an admin approves it.
"""
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Column, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, text

from app.Branches.model import CURRENCY, HEAD_OFFICE_ID
from app.database.database import db
from base_model import Base
from app.utils.dates import iso
from app.utils.money import as_str

PAYMENT_METHODS = ("bank_transfer", "mpesa", "cheque", "cash")

DEPOSIT_POSTED = "posted"
DEPOSIT_REVERSED = "reversed"

WITHDRAWAL_PENDING = "pending"
WITHDRAWAL_APPROVED = "approved"
WITHDRAWAL_REJECTED = "rejected"


def _utcnow():
    return datetime.now(timezone.utc)


class Deposit(Base, db.Model):
    __tablename__ = "deposits"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_deposits_amount_positive"),
        CheckConstraint("status IN ('posted', 'reversed')", name="ck_deposits_status"),
        CheckConstraint(
            "method IN ('bank_transfer', 'mpesa', 'cheque', 'cash')", name="ck_deposits_method"
        ),
        CheckConstraint("currency = 'KES'", name="ck_deposits_currency_kes"),
        Index("ix_deposits_investor_value_date", "investor_id", "value_date"),
        # The same receipt can't be recorded twice, whatever its letter case.
        Index("uq_deposits_reference_lower", text("lower(reference)"), unique=True),
    )

    id = Column(Integer, primary_key=True)
    investor_id = Column(Integer, ForeignKey("investors.id", ondelete="RESTRICT"), nullable=False)
    amount = Column(Numeric(20, 2), nullable=False)
    currency = Column(String(3), nullable=False, default=CURRENCY, server_default=CURRENCY)
    branch_id = Column(Integer, ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False, index=True,
                       default=HEAD_OFFICE_ID, server_default=str(HEAD_OFFICE_ID))
    value_date = Column(Date, nullable=False)  # date the money was received
    method = Column(String(20), nullable=False)
    reference = Column(String(100), nullable=False)  # bank / M-Pesa / cheque reference
    notes = Column(Text, nullable=True)

    status = Column(String(10), nullable=False, default=DEPOSIT_POSTED, server_default=DEPOSIT_POSTED)
    recorded_by = Column(String(120), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    reversed_by = Column(String(120), nullable=True)
    reversed_at = Column(DateTime(timezone=True), nullable=True)
    reversal_reason = Column(Text, nullable=True)

    investor = db.relationship("Investor", backref=db.backref("deposits", lazy="dynamic"))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "investor_id": self.investor_id,
            "client_code": self.investor.client_code if self.investor else None,
            "investor_name": self.investor.full_name if self.investor else None,
            "amount": as_str(self.amount),
            "currency": self.currency,
            "branch_id": self.branch_id,
            "value_date": iso(self.value_date),
            "method": self.method,
            "reference": self.reference,
            "notes": self.notes,
            "status": self.status,
            "recorded_by": self.recorded_by,
            "created_at": iso(self.created_at),
            "reversed_by": self.reversed_by,
            "reversed_at": iso(self.reversed_at),
            "reversal_reason": self.reversal_reason,
        }


class Withdrawal(Base, db.Model):
    """
    Maker-checker: staff records the request (pending); a *different* admin
    approves or rejects it. Only an approved withdrawal reduces the balance,
    from its value_date, which is set at approval time.
    """

    __tablename__ = "withdrawals"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_withdrawals_amount_positive"),
        CheckConstraint("status IN ('pending', 'approved', 'rejected')", name="ck_withdrawals_status"),
        CheckConstraint(
            "method IN ('bank_transfer', 'mpesa', 'cheque', 'cash')", name="ck_withdrawals_method"
        ),
        CheckConstraint(
            "(status = 'approved') = (value_date IS NOT NULL)", name="ck_withdrawals_value_date_iff_approved"
        ),
        CheckConstraint("currency = 'KES'", name="ck_withdrawals_currency_kes"),
        Index("ix_withdrawals_investor_value_date", "investor_id", "value_date"),
        Index("ix_withdrawals_status", "status"),
    )

    id = Column(Integer, primary_key=True)
    investor_id = Column(Integer, ForeignKey("investors.id", ondelete="RESTRICT"), nullable=False)
    amount = Column(Numeric(20, 2), nullable=False)
    currency = Column(String(3), nullable=False, default=CURRENCY, server_default=CURRENCY)
    branch_id = Column(Integer, ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False, index=True,
                       default=HEAD_OFFICE_ID, server_default=str(HEAD_OFFICE_ID))
    requested_date = Column(Date, nullable=False)  # date the investor asked
    method = Column(String(20), nullable=False)
    notes = Column(Text, nullable=True)

    status = Column(String(10), nullable=False, default=WITHDRAWAL_PENDING, server_default=WITHDRAWAL_PENDING)
    requested_by = Column(String(120), nullable=False)  # maker
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    decided_by = Column(String(120), nullable=True)  # checker
    decided_at = Column(DateTime(timezone=True), nullable=True)
    value_date = Column(Date, nullable=True)  # effective date of the balance reduction (approved only)
    payment_reference = Column(String(100), nullable=True)
    rejection_reason = Column(Text, nullable=True)

    investor = db.relationship("Investor", backref=db.backref("withdrawals", lazy="dynamic"))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "investor_id": self.investor_id,
            "client_code": self.investor.client_code if self.investor else None,
            "investor_name": self.investor.full_name if self.investor else None,
            "amount": as_str(self.amount),
            "currency": self.currency,
            "branch_id": self.branch_id,
            "requested_date": iso(self.requested_date),
            "method": self.method,
            "notes": self.notes,
            "status": self.status,
            "requested_by": self.requested_by,
            "created_at": iso(self.created_at),
            "decided_by": self.decided_by,
            "decided_at": iso(self.decided_at),
            "value_date": iso(self.value_date),
            "payment_reference": self.payment_reference,
            "rejection_reason": self.rejection_reason,
        }
