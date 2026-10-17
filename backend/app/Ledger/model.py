"""
General ledger (docs/architecture/03-general-ledger.md, FSD v0.1 §13).

Chart of accounts. Journals reference an account by id, never by code, so a
code can change without touching history. Accounts are never deleted (a
trigger refuses it): an account that is no longer wanted is deactivated.
Changes go through the gl.account.create / gl.account.change change requests.
"""
from sqlalchemy import (BigInteger, Boolean, CheckConstraint, Column, Date, DateTime, FetchedValue, ForeignKey,
                        ForeignKeyConstraint, Index, Integer, Numeric, String, Text, UniqueConstraint)
from sqlalchemy.orm import relationship

from app.database.database import db
from app.utils.dates import iso
from app.utils.money import as_str
from base_model import Base

ACCOUNT_TYPES = ("asset", "liability", "equity", "income", "expense")
SIDES = ("debit", "credit")
# The usual side for each type; contra accounts (provisions, suspense, depreciation) take the other.
DEFAULT_SIDE = {"asset": "debit", "expense": "debit", "liability": "credit", "equity": "credit", "income": "credit"}
ACCOUNT_SOURCES = ("working_assumption", "client_confirmed", "internal_decision")
CODE_PATTERN = r"^[0-9A-Za-z][0-9A-Za-z.\-]{0,19}$"


def _in(column: str, values) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class GlAccount(Base, db.Model):
    __tablename__ = "gl_accounts"
    __table_args__ = (
        CheckConstraint(_in("account_type", ACCOUNT_TYPES), name="ck_gl_accounts_type"),
        CheckConstraint(_in("normal_side", SIDES), name="ck_gl_accounts_normal_side"),
        CheckConstraint(_in("source", ACCOUNT_SOURCES), name="ck_gl_accounts_source"),
        CheckConstraint("currency = 'KES'", name="ck_gl_accounts_currency_kes"),
        CheckConstraint(f"code ~ '{CODE_PATTERN}'", name="ck_gl_accounts_code_format"),
        CheckConstraint("parent_id IS NULL OR parent_id <> id", name="ck_gl_accounts_not_own_parent"),
        CheckConstraint("is_postable OR NOT is_control", name="ck_gl_accounts_header_not_control"),
    )

    id = Column(Integer, primary_key=True)
    code = Column(String(20), nullable=False, unique=True)
    name = Column(String(150), nullable=False)
    account_type = Column(String(10), nullable=False)
    normal_side = Column(String(6), nullable=False)
    parent_id = Column(Integer, ForeignKey("gl_accounts.id", ondelete="RESTRICT"), nullable=True, index=True)
    is_postable = Column(Boolean, nullable=False, default=True)      # False = header (grouping only)
    is_control = Column(Boolean, nullable=False, default=False)      # lines must name a subledger account
    branch_id = Column(Integer, ForeignKey("branches.id", ondelete="RESTRICT"), nullable=True)  # NULL = every branch
    currency = Column(String(3), nullable=False, default="KES", server_default="KES")
    allow_manual_posting = Column(Boolean, nullable=False, default=True)
    is_active = Column(Boolean, nullable=False, default=True)
    source = Column(String(20), nullable=False, default="internal_decision")
    description = Column(Text, nullable=True)
    version = Column(Integer, nullable=False, default=1)              # bumped on every change (staleness)
    created_by = Column(String(120), nullable=False)
    updated_by = Column(String(120), nullable=True)

    def to_dict(self) -> dict:
        return {"id": self.id, "code": self.code, "name": self.name, "account_type": self.account_type,
                "normal_side": self.normal_side, "parent_id": self.parent_id, "is_postable": self.is_postable,
                "is_control": self.is_control, "branch_id": self.branch_id, "currency": self.currency,
                "allow_manual_posting": self.allow_manual_posting, "is_active": self.is_active,
                "source": self.source, "description": self.description, "version": self.version}


# ── Periods and journals ──
#
# Database rules (migration f2a2b3c4d5e6), not just Python:
#   * an entry needs >= 2 lines and its debits must equal its credits (checked at COMMIT);
#   * entries and lines are never updated or deleted; a correction is a reversal (reversal_of,
#     unique, and a reversal can't itself be reversed);
#   * nothing is posted into a closed period, and lines are only added in the entry's own transaction;
#   * lines use the entry's currency (composite FK) and an active, postable account, with a subledger
#     account exactly when the account is a control account;
#   * the journal number is allocated by the insert trigger: JV-<financial year>-000001, gapless per
#     financial year (the sequence row stays locked until the posting transaction ends).

PERIOD_OPEN, PERIOD_CLOSED = "open", "closed"
PERIOD_STATUSES = (PERIOD_OPEN, PERIOD_CLOSED)
ENTRY_POSTED = "posted"


class GlPeriod(Base, db.Model):
    __tablename__ = "gl_periods"
    __table_args__ = (
        CheckConstraint(_in("status", PERIOD_STATUSES), name="ck_gl_periods_status"),
        CheckConstraint("extract(day FROM period_start) = 1 AND period_end = "
                        "(period_start + interval '1 month' - interval '1 day')::date", name="ck_gl_periods_month"),
        CheckConstraint("(status = 'closed') = (closed_by IS NOT NULL AND closed_at IS NOT NULL)",
                        name="ck_gl_periods_closed"),
    )

    id = Column(Integer, primary_key=True)
    period_start = Column(Date, nullable=False, unique=True)
    period_end = Column(Date, nullable=False)
    financial_year = Column(Integer, nullable=False)     # the calendar year the financial year ends in
    status = Column(String(6), nullable=False, default=PERIOD_OPEN)
    closed_by = Column(String(120), nullable=True)
    closed_at = Column(DateTime(timezone=True), nullable=True)
    reopen_count = Column(Integer, nullable=False, default=0)
    last_change_request_id = Column(Integer, ForeignKey("change_requests.id", ondelete="RESTRICT"), nullable=True)
    created_by = Column(String(120), nullable=False)

    @property
    def label(self) -> str:
        return self.period_start.strftime("%Y-%m")

    def to_dict(self) -> dict:
        return {"id": self.id, "period": self.label, "period_start": iso(self.period_start),
                "period_end": iso(self.period_end), "financial_year": self.financial_year, "status": self.status,
                "closed_by": self.closed_by, "closed_at": iso(self.closed_at), "reopen_count": self.reopen_count}


class GlJournalSequence(db.Model):
    """Last journal number used per financial year. Written only by the journal_entries insert trigger."""
    __tablename__ = "gl_journal_sequences"

    financial_year = Column(Integer, primary_key=True)
    last_value = Column(Integer, nullable=False)


class JournalEntry(Base, db.Model):
    __tablename__ = "journal_entries"
    __table_args__ = (
        CheckConstraint(f"status = '{ENTRY_POSTED}'", name="ck_journal_entries_status"),
        CheckConstraint("currency = 'KES'", name="ck_journal_entries_currency_kes"),
        CheckConstraint("reversal_of IS NULL OR reason IS NOT NULL", name="ck_journal_entries_reversal_reason"),
        CheckConstraint("approved_by IS NULL OR lower(approved_by) <> lower(created_by)",
                        name="ck_journal_entries_maker_not_checker"),
        CheckConstraint("(source_type IS NULL) = (source_id IS NULL)", name="ck_journal_entries_source"),
        UniqueConstraint("id", "currency", name="uq_journal_entries_id_currency"),
        UniqueConstraint("financial_year", "seq_no", name="uq_journal_entries_year_seq"),
    )

    id = Column(Integer, primary_key=True)
    journal_no = Column(String(24), nullable=False, unique=True, server_default=FetchedValue())
    financial_year = Column(Integer, nullable=False, server_default=FetchedValue())
    seq_no = Column(Integer, nullable=False, server_default=FetchedValue())
    entry_date = Column(Date, nullable=False)              # the day it was posted (Nairobi)
    value_date = Column(Date, nullable=False, index=True)  # the business date: decides period and balances
    period_id = Column(Integer, ForeignKey("gl_periods.id", ondelete="RESTRICT"), nullable=False, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False)
    currency = Column(String(3), nullable=False, default="KES", server_default="KES")
    description = Column(Text, nullable=False)
    event_type = Column(String(60), nullable=True)
    source_type = Column(String(40), nullable=True)
    source_id = Column(String(64), nullable=True)
    status = Column(String(6), nullable=False, default=ENTRY_POSTED, server_default=ENTRY_POSTED)
    reversal_of = Column(Integer, ForeignKey("journal_entries.id", ondelete="RESTRICT"), nullable=True, unique=True)
    reason = Column(Text, nullable=True)
    created_by = Column(String(120), nullable=False)
    approved_by = Column(String(120), nullable=True)
    posted_at = Column(DateTime(timezone=True), nullable=False)
    posted_txid = Column(BigInteger, nullable=False, server_default=FetchedValue())

    lines = relationship("JournalLine", primaryjoin="JournalEntry.id == foreign(JournalLine.entry_id)",
                         order_by="JournalLine.line_no", lazy="selectin", viewonly=True)

    def to_dict(self, with_lines: bool = True) -> dict:
        out = {"id": self.id, "journal_no": self.journal_no, "financial_year": self.financial_year,
               "entry_date": iso(self.entry_date), "value_date": iso(self.value_date), "period_id": self.period_id,
               "branch_id": self.branch_id, "currency": self.currency, "description": self.description,
               "event_type": self.event_type, "source_type": self.source_type, "source_id": self.source_id,
               "status": self.status, "reversal_of": self.reversal_of, "reason": self.reason,
               "created_by": self.created_by, "approved_by": self.approved_by, "posted_at": iso(self.posted_at)}
        if with_lines:
            out["lines"] = [line.to_dict() for line in self.lines]
        return out


class JournalLine(Base, db.Model):
    __tablename__ = "journal_lines"
    __table_args__ = (
        CheckConstraint("(debit > 0 AND credit = 0) OR (credit > 0 AND debit = 0)", name="ck_journal_lines_one_side"),
        CheckConstraint("currency = 'KES'", name="ck_journal_lines_currency_kes"),
        ForeignKeyConstraint(["entry_id", "currency"], ["journal_entries.id", "journal_entries.currency"],
                             name="fk_journal_lines_entry_currency", ondelete="RESTRICT"),
        UniqueConstraint("entry_id", "line_no", name="uq_journal_lines_entry_line"),
        Index("ix_journal_lines_gl_account_branch", "gl_account_id", "branch_id"),
    )

    id = Column(Integer, primary_key=True)
    entry_id = Column(Integer, ForeignKey("journal_entries.id", ondelete="RESTRICT"), nullable=False, index=True)
    line_no = Column(Integer, nullable=False)
    gl_account_id = Column(Integer, ForeignKey("gl_accounts.id", ondelete="RESTRICT"), nullable=False)
    debit = Column(Numeric(20, 2), nullable=False, default=0)
    credit = Column(Numeric(20, 2), nullable=False, default=0)
    branch_id = Column(Integer, ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=True, index=True)
    party_id = Column(Integer, ForeignKey("parties.id", ondelete="RESTRICT"), nullable=True)
    currency = Column(String(3), nullable=False, default="KES", server_default="KES")
    description = Column(Text, nullable=True)

    def to_dict(self) -> dict:
        return {"id": self.id, "line_no": self.line_no, "gl_account_id": self.gl_account_id,
                "debit": as_str(self.debit), "credit": as_str(self.credit), "branch_id": self.branch_id,
                "account_id": self.account_id, "party_id": self.party_id, "currency": self.currency,
                "description": self.description}
