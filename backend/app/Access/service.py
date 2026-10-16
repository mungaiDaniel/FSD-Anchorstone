"""
What a user may do: permissions, branch scope and amount limits.

Everything is read from the database (never from the JWT), once per request
for permissions (cached on `g` by app/auth.py).
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import or_

from app.Access.model import Permission, Role, RolePermission, TransactionLimit, UserBranchScope, UserRole
from app.Admin.model import User
from app.database.database import db
from app.utils.dates import today_eat


def role_ids_for(user: User) -> list[int]:
    """The active roles a user holds: their primary built-in role plus any extra roles."""
    primary = db.session.query(Role.id).filter(Role.legacy_role == user.role, Role.active.is_(True))
    extra = (db.session.query(Role.id).join(UserRole, UserRole.role_id == Role.id)
             .filter(UserRole.user_id == user.id, Role.active.is_(True)))
    return sorted({rid for (rid,) in primary.union(extra).all()})


def permissions_for(user: User) -> frozenset[str]:
    role_ids = role_ids_for(user)
    if not role_ids:
        return frozenset()
    rows = (db.session.query(RolePermission.permission_code)
            .filter(RolePermission.role_id.in_(role_ids)).distinct().all())
    return frozenset(code for (code,) in rows)


def branch_scope(user: User) -> frozenset[int] | None:
    """Branch ids the user may act on, or None for every branch."""
    role_ids = role_ids_for(user)
    if role_ids and db.session.query(Role.id).filter(Role.id.in_(role_ids), Role.all_branches.is_(True)).first():
        return None
    rows = UserBranchScope.query.filter_by(user_id=user.id).all()
    if any(r.all_branches for r in rows):
        return None
    if rows:
        return frozenset(r.branch_id for r in rows)
    return frozenset({user.branch_id})


def in_branch_scope(user: User, branch_id: int | None) -> bool:
    scope = branch_scope(user)
    return scope is None or branch_id is None or branch_id in scope


@dataclass(frozen=True)
class Limit:
    configured: bool               # False: no limit row applies, so no amount may be decided
    max_per_item: Decimal | None   # None with configured=True: unlimited
    source: str | None = None      # "user" / "role:<code>"

    def allows(self, amount: Decimal) -> bool:
        return self.configured and (self.max_per_item is None or amount <= self.max_per_item)


def _current_limits(subject_type: str, subject_ids, permission: str, on: date):
    """The latest limit per subject with effective_from <= on."""
    rows = (TransactionLimit.query
            .filter(TransactionLimit.subject_type == subject_type,
                    TransactionLimit.subject_id.in_(list(subject_ids)),
                    TransactionLimit.permission_code == permission,
                    TransactionLimit.effective_from <= on)
            .order_by(TransactionLimit.subject_id, TransactionLimit.effective_from.desc()).all())
    latest = {}
    for row in rows:
        latest.setdefault(row.subject_id, row)
    return latest


def limit_for(user: User, permission: str, on: date | None = None) -> Limit:
    """
    The user's own limit if one is set, else the highest of their roles' limits.
    Only meaningful for amount_limited permissions; any other permission is unlimited.
    """
    perm = db.session.get(Permission, permission)
    if perm is None or not perm.amount_limited:
        return Limit(True, None, None)
    on = on or today_eat()
    own = _current_limits("user", [user.id], permission, on).get(user.id)
    if own is not None:
        return Limit(True, own.max_per_item, "user")
    role_ids = role_ids_for(user)
    by_role = _current_limits("role", role_ids, permission, on) if role_ids else {}
    if not by_role:
        return Limit(False, None, None)
    codes = dict(db.session.query(Role.id, Role.code).filter(Role.id.in_(list(by_role))).all())
    unlimited = [rid for rid, row in by_role.items() if row.max_per_item is None]
    if unlimited:
        return Limit(True, None, f"role:{codes[unlimited[0]]}")
    best_id, best = max(by_role.items(), key=lambda kv: kv[1].max_per_item)
    return Limit(True, best.max_per_item, f"role:{codes[best_id]}")


def users_with_permission(permission: str):
    """Active users holding a permission through any active role (for inbox and notifications)."""
    role_ids = [rid for (rid,) in db.session.query(RolePermission.role_id)
                .filter(RolePermission.permission_code == permission)]
    legacy = [lr for (lr,) in db.session.query(Role.legacy_role)
              .filter(Role.id.in_(role_ids), Role.active.is_(True), Role.legacy_role.isnot(None))]
    extra = db.session.query(UserRole.user_id).join(Role, Role.id == UserRole.role_id).filter(
        UserRole.role_id.in_(role_ids), Role.active.is_(True))
    return User.query.filter(User.status == "active",
                             or_(User.role.in_(legacy), User.id.in_(extra))).all()
