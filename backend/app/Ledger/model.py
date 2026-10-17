"""
General ledger (docs/architecture/03-general-ledger.md, FSD v0.1 §13).

Chart of accounts. Journals reference an account by id, never by code, so a
code can change without touching history. Accounts are never deleted (a
trigger refuses it): an account that is no longer wanted is deactivated.
Changes go through the gl.account.create / gl.account.change change requests.
"""
from sqlalchemy import Boolean, CheckConstraint, Column, ForeignKey, Integer, String, Text

from app.database.database import db
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
