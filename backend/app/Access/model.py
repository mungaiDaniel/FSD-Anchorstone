"""
Roles and permissions (ADR-04-4).

A permission is a fine-grained code ("withdrawal.approve"). A role is a bundle
of permissions. A user has one *primary* role in `user.role` (the three
built-in roles user / admin / super_admin, mapped through `roles.legacy_role`)
plus any number of extra roles in `user_roles`. Their permissions are the union
of every active role they hold.

Branch scope (`user_branch_scopes`) limits which branches' records a user may
act on; roles flagged `all_branches` see every branch. Transaction limits cap
the amount a user may decide for an `amount_limited` permission: the user's own
limit if set, otherwise the highest of their roles' limits (NULL = unlimited).
No limit row at all means the amount can't be decided (deny by default).

Role, limit and scope changes go through change requests (app/Approvals).
"""
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)

from app.database.database import db
from app.utils.dates import iso
from app.utils.money import as_str
from base_model import Base

LIMIT_SUBJECTS = ("role", "user")
SOD_SEVERITIES = ("block", "warn")


class Department(Base, db.Model):
    __tablename__ = "departments"

    id = Column(Integer, primary_key=True)
    code = Column(String(10), nullable=False, unique=True)
    name = Column(String(100), nullable=False)


class Permission(Base, db.Model):
    __tablename__ = "permissions"

    code = Column(String(80), primary_key=True)
    module = Column(String(40), nullable=False)
    description = Column(Text, nullable=False)
    # Viewing it exposes sensitive personal or financial data.
    sensitive = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    # Deciding it is capped by transaction_limits.
    amount_limited = Column(Boolean, nullable=False, default=False, server_default=text("false"))

    def to_dict(self) -> dict:
        return {"code": self.code, "module": self.module, "description": self.description,
                "sensitive": self.sensitive, "amount_limited": self.amount_limited}


class Role(Base, db.Model):
    __tablename__ = "roles"
    __table_args__ = (
        CheckConstraint("legacy_role IS NULL OR legacy_role IN ('user', 'admin', 'super_admin')",
                        name="ck_roles_legacy_role"),
    )

    id = Column(Integer, primary_key=True)
    code = Column(String(40), nullable=False, unique=True)
    name = Column(String(100), nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id", ondelete="RESTRICT"), nullable=True)
    description = Column(Text, nullable=True)
    built_in = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    # Only active roles grant their permissions.
    active = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    all_branches = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    # The value of user.role this role stands for (the three built-in roles only).
    legacy_role = Column(String(20), nullable=True, unique=True)

    department = db.relationship("Department")

    def permission_codes(self) -> list[str]:
        return sorted(code for (code,) in db.session.query(RolePermission.permission_code)
                      .filter(RolePermission.role_id == self.id))

    def to_dict(self, with_permissions: bool = False) -> dict:
        out = {"id": self.id, "code": self.code, "name": self.name, "description": self.description,
               "department": self.department.code if self.department else None, "built_in": self.built_in,
               "active": self.active, "all_branches": self.all_branches, "legacy_role": self.legacy_role}
        if with_permissions:
            out["permissions"] = self.permission_codes()
        return out


class RolePermission(Base, db.Model):
    __tablename__ = "role_permissions"

    role_id = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)
    permission_code = Column(String(80), ForeignKey("permissions.code", ondelete="RESTRICT"), primary_key=True)


class UserRole(Base, db.Model):
    """An extra role granted to a user on top of their primary role."""

    __tablename__ = "user_roles"
    __table_args__ = (UniqueConstraint("user_id", "role_id", name="uq_user_roles_user_role"),)

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    role_id = Column(Integer, ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False)
    granted_by = Column(String(120), nullable=False)
    granted_at = Column(DateTime(timezone=True), nullable=False)
    via_change_request_id = Column(Integer, nullable=True)

    role = db.relationship("Role")


class UserBranchScope(Base, db.Model):
    __tablename__ = "user_branch_scopes"
    __table_args__ = (
        CheckConstraint("all_branches = (branch_id IS NULL)", name="ck_user_branch_scopes_all_or_one"),
        Index("uq_user_branch_scopes_user_branch", "user_id", text("coalesce(branch_id, 0)"), unique=True),
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id", ondelete="RESTRICT"), nullable=True)
    all_branches = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    granted_by = Column(String(120), nullable=False)


class TransactionLimit(Base, db.Model):
    __tablename__ = "transaction_limits"
    __table_args__ = (
        CheckConstraint("subject_type IN ('role', 'user')", name="ck_transaction_limits_subject"),
        CheckConstraint("currency = 'KES'", name="ck_transaction_limits_currency_kes"),
        CheckConstraint("max_per_item IS NULL OR max_per_item > 0", name="ck_transaction_limits_item_positive"),
        CheckConstraint("max_per_day IS NULL OR max_per_day > 0", name="ck_transaction_limits_day_positive"),
        UniqueConstraint("subject_type", "subject_id", "permission_code", "effective_from",
                         name="uq_transaction_limits_subject_perm_date"),
    )

    id = Column(Integer, primary_key=True)
    subject_type = Column(String(10), nullable=False)
    subject_id = Column(Integer, nullable=False)
    permission_code = Column(String(80), ForeignKey("permissions.code", ondelete="RESTRICT"), nullable=False)
    currency = Column(String(3), nullable=False, default="KES", server_default="KES")
    max_per_item = Column(Numeric(20, 2), nullable=True)  # NULL = unlimited
    max_per_day = Column(Numeric(20, 2), nullable=True)
    effective_from = Column(Date, nullable=False)
    set_by = Column(String(120), nullable=False)

    def to_dict(self) -> dict:
        return {"id": self.id, "subject_type": self.subject_type, "subject_id": self.subject_id,
                "permission": self.permission_code, "currency": self.currency,
                "max_per_item": as_str(self.max_per_item), "max_per_day": as_str(self.max_per_day),
                "effective_from": iso(self.effective_from), "set_by": self.set_by}


class SodConflict(Base, db.Model):
    """Pairs of permissions one person shouldn't hold together."""

    __tablename__ = "sod_conflicts"
    __table_args__ = (CheckConstraint("severity IN ('block', 'warn')", name="ck_sod_conflicts_severity"),)

    permission_a = Column(String(80), ForeignKey("permissions.code", ondelete="RESTRICT"), primary_key=True)
    permission_b = Column(String(80), ForeignKey("permissions.code", ondelete="RESTRICT"), primary_key=True)
    severity = Column(String(5), nullable=False)
    reason = Column(Text, nullable=True)
