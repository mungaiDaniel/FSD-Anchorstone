"""
Branches. Every investor (and, later, every party, account and loan) belongs to
one. Anchorstone has a single branch today, Head Office (code 000, id 1), which
the migration creates; new branches are reference-data changes made through
maker-checker (phase 2b).

Money is KES only: every money table carries `currency CHAR(3) DEFAULT 'KES'`
with a CHECK that it is 'KES'. Enabling another currency is a migration (it
needs revaluation and reporting), never a setting.
"""
from sqlalchemy import CheckConstraint, Column, Integer, String

from app.database.database import db
from base_model import Base

HEAD_OFFICE_ID = 1
CURRENCY = "KES"
BRANCH_STATUSES = ("active", "closed")


class Branch(Base, db.Model):
    __tablename__ = "branches"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'closed')", name="ck_branches_status"),
        CheckConstraint("code ~ '^[0-9]{3}$'", name="ck_branches_code_format"),
    )

    id = Column(Integer, primary_key=True)
    code = Column(String(3), nullable=False, unique=True)
    name = Column(String(100), nullable=False)
    status = Column(String(10), nullable=False, default="active", server_default="active")

    def to_dict(self) -> dict:
        return {"id": self.id, "code": self.code, "name": self.name, "status": self.status}
