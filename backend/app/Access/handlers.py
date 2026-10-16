"""
Role, limit and branch-scope changes — always through change requests, so a
second system administrator approves every change to who can do what.
"""
import hashlib
import json
from datetime import date
from decimal import Decimal, InvalidOperation

from app.Access.model import Permission, Role, SodConflict, TransactionLimit, UserBranchScope, UserRole
from app.Access.service import permissions_for
from app.Admin.model import User
from app.Approvals.handlers import Handler, register
from app.Branches.model import Branch
from app.database.database import db
from app.utils.dates import parse_date, today_eat, utcnow
from app.utils.http import ValidationError
from app.utils.money import as_str


def _fingerprint(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def _user(payload) -> User:
    try:
        user_id = int(payload.get("user_id"))
    except (TypeError, ValueError):
        raise ValidationError("user_id is required.")
    user = db.session.get(User, user_id)
    if user is None:
        raise ValidationError("User not found.")
    return user


def _role(payload) -> Role:
    role = Role.query.filter_by(code=(payload.get("role_code") or "").strip()).first()
    if role is None:
        raise ValidationError("Role not found.")
    return role


def sod_warnings(user: User, extra_permissions) -> list[str]:
    held = set(permissions_for(user)) | set(extra_permissions)
    out = []
    for c in SodConflict.query.all():
        if c.permission_a in held and c.permission_b in held:
            out.append(f"{c.severity}: {c.permission_a} with {c.permission_b} ({c.reason})")
    return out


class _RbacHandler(Handler):
    submit_permission = "role.manage"
    entity_type = "user"

    def entity_id(self, payload):
        return str(payload.get("user_id")) if payload.get("user_id") is not None else None


@register
class GrantRole(_RbacHandler):
    request_type = "rbac.grant_role"

    def validate(self, payload):
        user, role = _user(payload), _role(payload)
        if role.legacy_role:
            raise ValidationError("Built-in roles are set as the user's primary role, not granted as extra roles.")
        if UserRole.query.filter_by(user_id=user.id, role_id=role.id).first():
            raise ValidationError(f"{user.email} already has the {role.name} role.")
        blocks = [w for w in sod_warnings(user, role.permission_codes()) if w.startswith("block")]
        if blocks:
            raise ValidationError("Segregation of duties: " + "; ".join(blocks))
        return {"user_id": user.id, "role_code": role.code}

    def describe(self, payload):
        user, role = db.session.get(User, payload["user_id"]), Role.query.filter_by(code=payload["role_code"]).first()
        return f"Grant {role.name if role else payload['role_code']} to {user.email if user else payload['user_id']}"

    def apply(self, request, actor):
        user, role = _user(request.payload), _role(request.payload)
        db.session.add(UserRole(user_id=user.id, role_id=role.id, granted_by=actor.email, granted_at=utcnow(),
                                via_change_request_id=request.id))
        return {"granted": role.code, "warnings": sod_warnings(user, [])}


@register
class RevokeRole(_RbacHandler):
    request_type = "rbac.revoke_role"

    def validate(self, payload):
        user, role = _user(payload), _role(payload)
        if not UserRole.query.filter_by(user_id=user.id, role_id=role.id).first():
            raise ValidationError(f"{user.email} doesn't have the {role.name} role.")
        return {"user_id": user.id, "role_code": role.code}

    def describe(self, payload):
        return f"Revoke {payload['role_code']} from user {payload['user_id']}"

    def apply(self, request, actor):
        user, role = _user(request.payload), _role(request.payload)
        UserRole.query.filter_by(user_id=user.id, role_id=role.id).delete()
        return {"revoked": role.code}


def _money_or_none(value, field):
    if value in (None, ""):
        return None
    try:
        amount = Decimal(str(value).replace(",", ""))
    except InvalidOperation:
        raise ValidationError(f"{field} must be an amount.")
    if amount <= 0 or amount != amount.quantize(Decimal("0.01")):
        raise ValidationError(f"{field} must be greater than 0 with at most 2 decimal places.")
    return amount


@register
class SetLimit(_RbacHandler):
    """{subject_type: user|role, user_id | role_code, permission, max_per_item (null = unlimited), effective_from}"""

    request_type = "rbac.set_limit"
    entity_type = "transaction_limit"

    def _subject(self, payload):
        if payload.get("subject_type") == "user":
            return "user", _user(payload).id
        if payload.get("subject_type") == "role":
            return "role", _role(payload).id
        raise ValidationError("subject_type must be 'user' or 'role'.")

    def entity_id(self, payload):
        return f"{payload['subject_type']}:{payload['subject_id']}:{payload['permission']}"

    def validate(self, payload):
        subject_type, subject_id = self._subject(payload)
        perm = db.session.get(Permission, payload.get("permission") or "")
        if perm is None or not perm.amount_limited:
            raise ValidationError("permission must be an amount-limited permission.")
        max_item = _money_or_none(payload.get("max_per_item"), "max_per_item")
        max_day = _money_or_none(payload.get("max_per_day"), "max_per_day")
        effective = parse_date(payload.get("effective_from"), "effective_from", required=False) or today_eat()
        if effective < today_eat():
            raise ValidationError("effective_from can't be in the past.")
        out = {"subject_type": subject_type, "subject_id": subject_id, "permission": perm.code,
               "max_per_item": as_str(max_item), "max_per_day": as_str(max_day), "effective_from": effective.isoformat()}
        if subject_type == "role":
            out["role_code"] = payload.get("role_code")
        else:
            out["user_id"] = subject_id
        return out

    def describe(self, payload):
        cap = f"KES {payload['max_per_item']}" if payload.get("max_per_item") else "unlimited"
        return f"Set {payload['permission']} limit for {payload['subject_type']} {payload['subject_id']} to {cap}"

    def apply(self, request, actor):
        p = request.payload
        effective = date.fromisoformat(p["effective_from"])
        existing = TransactionLimit.query.filter_by(subject_type=p["subject_type"], subject_id=p["subject_id"],
                                                    permission_code=p["permission"], effective_from=effective).first()
        if existing is not None:
            raise ValidationError("A limit with this effective date already exists. Choose another date.")
        db.session.add(TransactionLimit(
            subject_type=p["subject_type"], subject_id=p["subject_id"], permission_code=p["permission"],
            max_per_item=Decimal(p["max_per_item"]) if p.get("max_per_item") else None,
            max_per_day=Decimal(p["max_per_day"]) if p.get("max_per_day") else None,
            effective_from=effective, set_by=actor.email))
        return {"limit": p}


@register
class SetBranchScope(_RbacHandler):
    """{user_id, all_branches: true} or {user_id, branch_ids: [..]} — replaces the user's scope."""

    request_type = "rbac.set_branch_scope"

    def _current(self, user_id):
        return sorted((r.branch_id or 0, r.all_branches) for r in UserBranchScope.query.filter_by(user_id=user_id))

    def base_version(self, payload):
        return _fingerprint(self._current(payload["user_id"]))

    def old_value(self, payload):
        return {"scope": self._current(payload["user_id"])}

    def validate(self, payload):
        user = _user(payload)
        if payload.get("all_branches") is True:
            return {"user_id": user.id, "all_branches": True, "branch_ids": []}
        ids = payload.get("branch_ids")
        if not isinstance(ids, list) or not ids:
            raise ValidationError("Give branch_ids (a list) or all_branches: true.")
        try:
            ids = sorted({int(i) for i in ids})
        except (TypeError, ValueError):
            raise ValidationError("branch_ids must be numbers.")
        if Branch.query.filter(Branch.id.in_(ids)).count() != len(ids):
            raise ValidationError("Unknown branch in branch_ids.")
        return {"user_id": user.id, "all_branches": False, "branch_ids": ids}

    def describe(self, payload):
        where = "all branches" if payload["all_branches"] else f"branches {payload['branch_ids']}"
        return f"Set branch access for user {payload['user_id']} to {where}"

    def apply(self, request, actor):
        p = request.payload
        UserBranchScope.query.filter_by(user_id=p["user_id"]).delete()
        if p["all_branches"]:
            db.session.add(UserBranchScope(user_id=p["user_id"], all_branches=True, granted_by=actor.email))
        for branch_id in p["branch_ids"]:
            db.session.add(UserBranchScope(user_id=p["user_id"], branch_id=branch_id, granted_by=actor.email))
        return {"scope": "all" if p["all_branches"] else p["branch_ids"]}


@register
class SetRoleActive(_RbacHandler):
    """{role_code, active} — switch a (non-built-in) role on or off."""

    request_type = "rbac.set_role_active"
    entity_type = "role"

    def entity_id(self, payload):
        return payload.get("role_code")

    def base_version(self, payload):
        role = Role.query.filter_by(code=payload["role_code"]).first()
        return str(role.active) if role else None

    def validate(self, payload):
        role = _role(payload)
        if role.built_in:
            raise ValidationError("Built-in roles can't be switched off.")
        if not isinstance(payload.get("active"), bool):
            raise ValidationError("active must be true or false.")
        return {"role_code": role.code, "active": payload["active"]}

    def describe(self, payload):
        return f"{'Activate' if payload['active'] else 'Deactivate'} role {payload['role_code']}"

    def apply(self, request, actor):
        role = _role(request.payload)
        role.active = request.payload["active"]
        return {"role": role.code, "active": role.active}
