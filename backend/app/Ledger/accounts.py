"""
Chart of accounts: lookups and the validation shared by the gl.account.*
change requests (app/Ledger/handlers.py).
"""
import re

from sqlalchemy import func

from app.Branches.model import Branch
from app.database.database import db
from app.Ledger.model import ACCOUNT_SOURCES, ACCOUNT_TYPES, CODE_PATTERN, DEFAULT_SIDE, SIDES, GlAccount
from app.utils.http import NotFound, ValidationError

EDITABLE = ("code", "name", "account_type", "normal_side", "parent_id", "is_postable", "is_control", "branch_id",
            "allow_manual_posting", "is_active", "description", "source")
# Fields that change what existing postings mean; refused once the account has lines.
FIXED_ONCE_USED = ("account_type", "normal_side", "is_postable", "is_control", "branch_id")


def get_account(account_id) -> GlAccount:
    account = db.session.get(GlAccount, account_id) if isinstance(account_id, int) else None
    if account is None:
        raise NotFound("GL account not found.")
    return account


def by_code(code: str) -> GlAccount | None:
    return GlAccount.query.filter(func.lower(GlAccount.code) == (code or "").strip().lower()).first()


def list_accounts(include_inactive: bool = True) -> list[GlAccount]:
    q = GlAccount.query
    if not include_inactive:
        q = q.filter(GlAccount.is_active.is_(True))
    return q.order_by(GlAccount.code).all()


def has_postings(account: GlAccount) -> bool:
    from app.Ledger.model import JournalLine
    return db.session.query(JournalLine.id).filter(JournalLine.gl_account_id == account.id).first() is not None


def children(account: GlAccount) -> list[GlAccount]:
    return GlAccount.query.filter(GlAccount.parent_id == account.id).all()


def _descendant_ids(account: GlAccount) -> set[int]:
    out, todo = set(), [account.id]
    while todo:
        ids = [a.id for a in GlAccount.query.filter(GlAccount.parent_id.in_(todo)).all()]
        todo = [i for i in ids if i not in out]
        out.update(todo)
    return out


# ── field validators ──


def _text(value, field: str, max_len: int, required: bool = True) -> str | None:
    if value is not None and not isinstance(value, str):
        raise ValidationError(f"{field} must be text.")
    value = (value or "").strip()
    if required and not value:
        raise ValidationError(f"{field} is required.")
    if len(value) > max_len:
        raise ValidationError(f"{field} must be at most {max_len} characters.")
    return value or None


def _bool(value, field: str) -> bool:
    if not isinstance(value, bool):
        raise ValidationError(f"{field} must be true or false.")
    return value


def _choice(value, field: str, choices) -> str:
    if value not in choices:
        raise ValidationError(f"{field} must be one of: {', '.join(choices)}.")
    return value


def _code(value, exclude_id: int | None = None) -> str:
    code = _text(value, "code", 20)
    if not re.match(CODE_PATTERN, code):
        raise ValidationError("code may use letters, digits, '.' and '-' only (up to 20 characters).")
    clash = by_code(code)
    if clash is not None and clash.id != exclude_id:
        raise ValidationError(f"Code {code} is already used by {clash.name}.")
    return code


def _branch(value) -> int | None:
    if value is None:
        return None
    branch = db.session.get(Branch, value) if isinstance(value, int) and not isinstance(value, bool) else None
    if branch is None or branch.status != "active":
        raise ValidationError("branch_id must be an active branch (or null for every branch).")
    return branch.id


def _parent(value, account_type: str, account: GlAccount | None = None) -> int | None:
    if value is None:
        return None
    parent = db.session.get(GlAccount, value) if isinstance(value, int) and not isinstance(value, bool) else None
    if parent is None:
        raise ValidationError("parent_id must be an existing GL account.")
    if parent.is_postable:
        raise ValidationError(f"{parent.code} {parent.name} takes postings; a parent must be a header account.")
    if not parent.is_active:
        raise ValidationError(f"{parent.code} {parent.name} is inactive.")
    if parent.account_type != account_type:
        raise ValidationError(f"The parent's type is {parent.account_type}; this account's is {account_type}.")
    if account is not None and (parent.id == account.id or parent.id in _descendant_ids(account)):
        raise ValidationError("An account can't sit under itself or one of its own sub-accounts.")
    return parent.id


def validate_new(payload: dict) -> dict:
    account_type = _choice(payload.get("account_type"), "account_type", ACCOUNT_TYPES)
    out = {
        "code": _code(payload.get("code")),
        "name": _text(payload.get("name"), "name", 150),
        "account_type": account_type,
        "normal_side": _choice(payload.get("normal_side") or DEFAULT_SIDE[account_type], "normal_side", SIDES),
        "parent_id": _parent(payload.get("parent_id"), account_type),
        "is_postable": _bool(payload.get("is_postable", True), "is_postable"),
        "is_control": _bool(payload.get("is_control", False), "is_control"),
        "branch_id": _branch(payload.get("branch_id")),
        "allow_manual_posting": _bool(payload.get("allow_manual_posting", True), "allow_manual_posting"),
        "description": _text(payload.get("description"), "description", 1000, required=False),
        "source": _choice(payload.get("source") or "internal_decision", "source", ACCOUNT_SOURCES),
    }
    if out["is_control"] and not out["is_postable"]:
        raise ValidationError("A header account can't be a control account.")
    return out


def validate_change(account: GlAccount, changes) -> dict:
    """Normalise a change set against the account's current state. Only fields that differ are kept."""
    if not isinstance(changes, dict) or not changes:
        raise ValidationError("changes must name at least one field.")
    unknown = set(changes) - set(EDITABLE)
    if unknown:
        raise ValidationError(f"These fields can't be changed: {', '.join(sorted(unknown))}.")
    new = account.to_dict()
    new.update(changes)
    account_type = _choice(new["account_type"], "account_type", ACCOUNT_TYPES)
    clean = {
        "code": _code(new["code"], exclude_id=account.id),
        "name": _text(new["name"], "name", 150),
        "account_type": account_type,
        "normal_side": _choice(new["normal_side"], "normal_side", SIDES),
        "parent_id": _parent(new["parent_id"], account_type, account) if new["parent_id"] != account.parent_id
        or account_type != account.account_type else account.parent_id,
        "is_postable": _bool(new["is_postable"], "is_postable"),
        "is_control": _bool(new["is_control"], "is_control"),
        "branch_id": _branch(new["branch_id"]) if new["branch_id"] != account.branch_id else account.branch_id,
        "allow_manual_posting": _bool(new["allow_manual_posting"], "allow_manual_posting"),
        "is_active": _bool(new["is_active"], "is_active"),
        "description": _text(new["description"], "description", 1000, required=False),
        "source": _choice(new["source"], "source", ACCOUNT_SOURCES),
    }
    diff = {k: v for k, v in clean.items() if v != getattr(account, k)}
    if not diff:
        raise ValidationError("Nothing would change.")
    if clean["is_control"] and not clean["is_postable"]:
        raise ValidationError("A header account can't be a control account.")

    kids = children(account)
    if "account_type" in diff and kids:
        raise ValidationError("Change the type of the sub-accounts first; a header and its sub-accounts share a type.")
    if diff.get("is_postable") is True and kids:
        raise ValidationError("This header has sub-accounts, so it can't take postings.")
    if diff.get("is_active") is False and any(k.is_active for k in kids):
        raise ValidationError("Deactivate the sub-accounts first.")
    if diff.get("is_active") is True and account.parent_id is not None:
        parent = db.session.get(GlAccount, clean["parent_id"])
        if parent is not None and not parent.is_active:
            raise ValidationError(f"The parent {parent.code} is inactive; reactivate it first.")
    used = [f for f in FIXED_ONCE_USED if f in diff]
    if used and has_postings(account):
        raise ValidationError(f"The account has postings, so {', '.join(used)} can't change. "
                              "Open a new account and deactivate this one instead.")
    return diff
