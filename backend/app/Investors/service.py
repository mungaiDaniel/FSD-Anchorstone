"""
Investor accounts: one running balance per investor.
"""
import re

from sqlalchemy import func, or_

from app.database.database import db
from app.Interest.model import PAYOUT_PENDING, InterestPayout
from app.Investors.model import INVESTOR_STATUSES, PAYOUT_METHODS, Investor, client_code_seq
from app.Transactions.ledger import balances_subquery, investor_totals, lock_investor
from app.utils.audit_log import create_audit_log
from app.utils.dates import utcnow
from app.utils.http import Conflict, NotFound, ValidationError
from app.utils.money import as_str

EDITABLE_FIELDS = {
    "full_name": 150,
    "email": 150,
    "phone": 30,
    "id_number": 50,
    "kra_pin": 20,
    "payout_method": 10,
    "bank_name": 100,
    "payout_account": 100,
    "notes": None,
}
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def get_investor(investor_id: int) -> Investor:
    investor = db.session.get(Investor, investor_id)
    if investor is None:
        raise NotFound("Investor not found.")
    return investor


def _clean(data: dict, *, partial: bool) -> dict:
    values = {}
    for field, max_len in EDITABLE_FIELDS.items():
        if field not in data:
            continue
        raw = data.get(field)
        value = str(raw).strip() if raw is not None else ""
        if max_len and len(value) > max_len:
            raise ValidationError(f"{field} must be at most {max_len} characters.")
        values[field] = value or None

    if not partial or "full_name" in values:
        if not values.get("full_name"):
            raise ValidationError("full_name is required.")
    if not partial or "email" in values:
        email = (values.get("email") or "").lower()
        if not EMAIL_RE.match(email):
            raise ValidationError("A valid email is required — statements are sent to it.")
        values["email"] = email
    if values.get("payout_method") is not None:
        values["payout_method"] = values["payout_method"].lower()
        if values["payout_method"] not in PAYOUT_METHODS:
            raise ValidationError(f"payout_method must be one of: {', '.join(PAYOUT_METHODS)}.")
    if values.get("kra_pin"):
        values["kra_pin"] = values["kra_pin"].upper()
    return values


def _assert_email_free(email: str, exclude_id: int | None = None) -> None:
    q = db.session.query(Investor.id, Investor.client_code).filter(func.lower(Investor.email) == email.lower())
    if exclude_id is not None:
        q = q.filter(Investor.id != exclude_id)
    clash = q.first()
    if clash:
        raise Conflict(f"Investor {clash.client_code} already uses this email. Each investor has one account.")


def create_investor(data: dict, actor: str) -> Investor:
    values = _clean(data, partial=False)
    _assert_email_free(values["email"])

    number = db.session.execute(client_code_seq.next_value()).scalar()
    investor = Investor(client_code=f"ACL-{number:06d}", created_by=actor, status="active", **values)
    db.session.add(investor)
    db.session.commit()
    create_audit_log("CREATE_INVESTOR", target_type="investor", target_id=investor.id,
                     target_name=investor.client_code, new_value=investor.to_dict())
    return investor


def update_investor(investor_id: int, data: dict, actor: str) -> Investor:
    investor = get_investor(investor_id)
    values = _clean(data, partial=True)
    if "email" in values:
        _assert_email_free(values["email"], exclude_id=investor.id)

    old = {k: getattr(investor, k) for k in values}
    for key, value in values.items():
        setattr(investor, key, value)
    db.session.commit()
    create_audit_log("UPDATE_INVESTOR", target_type="investor", target_id=investor.id,
                     target_name=investor.client_code, old_value=old, new_value=values)
    return investor


def set_investor_status(investor_id: int, data: dict, actor: str) -> Investor:
    status = str(data.get("status") or "").strip().lower()
    if status not in INVESTOR_STATUSES:
        raise ValidationError(f"status must be one of: {', '.join(INVESTOR_STATUSES)}.")
    investor = lock_investor(investor_id)
    if investor.status == status:
        return investor

    if status == "closed":
        totals = investor_totals(investor.id)
        if totals["balance"] != 0:
            raise Conflict(f"The account still has a balance of KES {totals['balance']:,.2f}. Withdraw it before closing.")
        if totals["pending_withdrawals"] != 0:
            raise Conflict("The account has a pending withdrawal. Approve or reject it before closing.")
        unpaid = db.session.query(InterestPayout.id).filter(
            InterestPayout.investor_id == investor.id, InterestPayout.status == PAYOUT_PENDING
        ).first()
        if unpaid:
            raise Conflict("The account has interest that hasn't been paid out yet. Mark it paid before closing.")
        investor.closed_at = utcnow()
    else:
        investor.closed_at = None

    old = investor.status
    investor.status = status
    db.session.commit()
    create_audit_log("SET_INVESTOR_STATUS", target_type="investor", target_id=investor.id,
                     target_name=investor.client_code, old_value={"status": old}, new_value={"status": status})
    return investor


def investor_summary(investor: Investor) -> dict:
    totals = investor_totals(investor.id)
    return {**investor.to_dict(), **{k: as_str(v) for k, v in totals.items()}}


def apply_investor_filters(q, search: str | None, status: str | None):
    """The investor list's search and status filter — shared with bulk-email
    recipient selection, so "select all filtered" means exactly what's on screen."""
    if status in INVESTOR_STATUSES:
        q = q.filter(Investor.status == status)
    if search and search.strip():
        like = f"%{search.strip()}%"
        q = q.filter(or_(
            Investor.full_name.ilike(like),
            Investor.email.ilike(like),
            Investor.client_code.ilike(like),
            Investor.phone.ilike(like),
            Investor.id_number.ilike(like),
        ))
    return q


def list_investors(search: str | None, status: str | None, page: int, per_page: int) -> dict:
    bal = balances_subquery()
    q = db.session.query(Investor, bal.c.balance, bal.c.pending_withdrawals).join(
        bal, bal.c.investor_id == Investor.id
    )
    q = apply_investor_filters(q, search, status)
    total = q.count()
    rows = q.order_by(Investor.full_name.asc()).limit(per_page).offset((page - 1) * per_page).all()
    return {
        "items": [
            {**inv.to_dict(), "balance": as_str(balance), "pending_withdrawals": as_str(pending)}
            for inv, balance, pending in rows
        ],
        "total": total,
        "page": page,
        "per_page": per_page,
    }
