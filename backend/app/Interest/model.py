"""
Interest: one flat annual rate for everyone (with a history of changes),
calculated monthly as simple interest on the daily closing balance and paid
out — never added to the balance.

    daily interest = closing balance that day × rate% ÷ 100 ÷ 365

Lifecycle of a month (InterestPeriod):
    draft     an admin calculated it; payouts can be reviewed, recalculated or discarded
    approved  a different admin approved it; statements are emailed, payouts await payment
    paid      every payout in it has been marked paid with a payment reference

Once a period is approved, its dates are locked: no deposit, withdrawal,
reversal or rate change can be backdated into it.
"""
from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)

from app.database.database import db
from base_model import Base
from app.utils.dates import iso
from app.utils.money import as_str

PERIOD_DRAFT = "draft"
PERIOD_APPROVED = "approved"
PERIOD_PAID = "paid"
LOCKED_PERIOD_STATUSES = (PERIOD_APPROVED, PERIOD_PAID)

PAYOUT_PENDING = "pending"
PAYOUT_PAID = "paid"


def _utcnow():
    return datetime.now(timezone.utc)


def _rate_str(value):
    return f"{value:.4f}" if value is not None else None


class InterestRate(Base, db.Model):
    __tablename__ = "interest_rates"
    __table_args__ = (CheckConstraint("rate_percent >= 0 AND rate_percent <= 100", name="ck_interest_rates_range"),)

    id = Column(Integer, primary_key=True)
    rate_percent = Column(Numeric(7, 4), nullable=False)  # annual, e.g. 12.5000 = 12.5% p.a.
    effective_from = Column(Date, nullable=False, unique=True)
    note = Column(Text, nullable=True)
    set_by = Column(String(120), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "rate_percent": _rate_str(self.rate_percent),
            "effective_from": iso(self.effective_from),
            "note": self.note,
            "set_by": self.set_by,
            "created_at": iso(self.created_at),
        }


class InterestPeriod(Base, db.Model):
    __tablename__ = "interest_periods"
    __table_args__ = (
        CheckConstraint("status IN ('draft', 'approved', 'paid')", name="ck_interest_periods_status"),
        CheckConstraint("period_end >= period_start", name="ck_interest_periods_dates"),
    )

    id = Column(Integer, primary_key=True)
    period_start = Column(Date, nullable=False, unique=True)
    period_end = Column(Date, nullable=False)
    status = Column(String(10), nullable=False, default=PERIOD_DRAFT, server_default=PERIOD_DRAFT)

    # Withholding tax is modelled but not applied yet: tax_rate stays 0 until
    # Anchorstone's compliance team confirms the treatment.
    tax_rate_percent = Column(Numeric(7, 4), nullable=False, default=0, server_default="0")

    investor_count = Column(Integer, nullable=False, default=0)
    total_gross = Column(Numeric(20, 2), nullable=False, default=0)
    total_tax = Column(Numeric(20, 2), nullable=False, default=0)
    total_net = Column(Numeric(20, 2), nullable=False, default=0)

    calculated_by = Column(String(120), nullable=False)
    calculated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    approved_by = Column(String(120), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    paid_at = Column(DateTime(timezone=True), nullable=True)

    payouts = db.relationship(
        "InterestPayout", back_populates="period", cascade="all, delete-orphan", lazy="dynamic"
    )

    @property
    def label(self) -> str:
        return self.period_start.strftime("%B %Y")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "period_start": iso(self.period_start),
            "period_end": iso(self.period_end),
            "status": self.status,
            "tax_rate_percent": _rate_str(self.tax_rate_percent),
            "investor_count": self.investor_count,
            "total_gross": as_str(self.total_gross),
            "total_tax": as_str(self.total_tax),
            "total_net": as_str(self.total_net),
            "calculated_by": self.calculated_by,
            "calculated_at": iso(self.calculated_at),
            "approved_by": self.approved_by,
            "approved_at": iso(self.approved_at),
            "paid_at": iso(self.paid_at),
        }


class InterestPayout(Base, db.Model):
    __tablename__ = "interest_payouts"
    __table_args__ = (
        UniqueConstraint("period_id", "investor_id", name="uq_interest_payouts_period_investor"),
        CheckConstraint("status IN ('pending', 'paid')", name="ck_interest_payouts_status"),
        CheckConstraint("net_interest = gross_interest - tax_amount", name="ck_interest_payouts_net"),
    )

    id = Column(Integer, primary_key=True)
    period_id = Column(Integer, ForeignKey("interest_periods.id", ondelete="CASCADE"), nullable=False, index=True)
    investor_id = Column(Integer, ForeignKey("investors.id", ondelete="RESTRICT"), nullable=False, index=True)

    days = Column(Integer, nullable=False)
    opening_balance = Column(Numeric(20, 2), nullable=False)
    closing_balance = Column(Numeric(20, 2), nullable=False)
    average_daily_balance = Column(Numeric(20, 2), nullable=False)
    # Effective annual rate for the period (equals the flat rate unless the rate
    # changed mid-month, in which case it's the day-weighted blend).
    rate_percent = Column(Numeric(7, 4), nullable=False)

    gross_interest = Column(Numeric(20, 2), nullable=False)
    tax_rate_percent = Column(Numeric(7, 4), nullable=False, default=0, server_default="0")
    tax_amount = Column(Numeric(20, 2), nullable=False, default=0, server_default="0")
    net_interest = Column(Numeric(20, 2), nullable=False)

    status = Column(String(10), nullable=False, default=PAYOUT_PENDING, server_default=PAYOUT_PENDING)
    paid_at = Column(DateTime(timezone=True), nullable=True)
    paid_by = Column(String(120), nullable=True)
    payment_reference = Column(String(100), nullable=True)

    period = db.relationship("InterestPeriod", back_populates="payouts")
    investor = db.relationship("Investor", backref=db.backref("interest_payouts", lazy="dynamic"))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "period_id": self.period_id,
            "period_label": self.period.label if self.period else None,
            "period_status": self.period.status if self.period else None,
            "investor_id": self.investor_id,
            "client_code": self.investor.client_code if self.investor else None,
            "investor_name": self.investor.full_name if self.investor else None,
            "days": self.days,
            "opening_balance": as_str(self.opening_balance),
            "closing_balance": as_str(self.closing_balance),
            "average_daily_balance": as_str(self.average_daily_balance),
            "rate_percent": _rate_str(self.rate_percent),
            "gross_interest": as_str(self.gross_interest),
            "tax_rate_percent": _rate_str(self.tax_rate_percent),
            "tax_amount": as_str(self.tax_amount),
            "net_interest": as_str(self.net_interest),
            "status": self.status,
            "paid_at": iso(self.paid_at),
            "paid_by": self.paid_by,
            "payment_reference": self.payment_reference,
        }
