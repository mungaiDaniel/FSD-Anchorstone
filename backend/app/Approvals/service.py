"""
Change-request lifecycle. Every transition writes an event and an audit entry
in the same transaction; the final approval applies the change in that same
transaction too, so a change is either applied, approved and audited, or none
of them.
"""
from datetime import timedelta

from sqlalchemy import func

from app.Access.service import in_branch_scope, permissions_for
from app.Admin.model import User
from app.Approvals.handlers import HANDLERS, Handler
from app.Approvals.model import (
    CR_APPLIED,
    CR_CANCELLED,
    CR_EXPIRED,
    CR_FAILED,
    CR_PENDING,
    CR_REJECTED,
    CR_RETURNED,
    ChangeRequest,
    ChangeRequestEvent,
)
from app.Approvals.policy import assert_level_rights, select_policy
from app.database.database import db
from app.utils.audit_log import create_audit_log
from app.utils.dates import utcnow
from app.utils.http import Conflict, Forbidden, NotFound, ValidationError

STALE_MESSAGE = "The record changed after this request was made. Submit a new request."
MAKER_MESSAGE = "Maker-checker: a change request must be decided by someone other than the person who made it."


def handler_for(request_type: str) -> Handler:
    handler = HANDLERS.get(request_type)
    if handler is None:
        raise ValidationError(f"Unknown request type: {request_type}.")
    return handler


def _text(value, field: str, required: bool = False) -> str | None:
    value = (value or "").strip() if isinstance(value, str) or value is None else None
    if value is None:
        raise ValidationError(f"{field} must be text.")
    if required and not value:
        raise ValidationError(f"{field} is required.")
    return value or None


def _event(cr: ChangeRequest, action: str, actor: User | None, *, level=None, comment=None) -> None:
    db.session.add(ChangeRequestEvent(request_id=cr.id, round=cr.round, action=action, level=level,
                                      actor_user_id=actor.id if actor else None,
                                      actor_email=actor.email if actor else "scheduler",
                                      comment=comment, at=utcnow()))
    db.session.flush()


def _audit(cr: ChangeRequest, action: str, description: str, **kw) -> None:
    kw.setdefault("new_value", {"status": cr.status, "payload": cr.payload})
    create_audit_log(f"CHANGE_REQUEST_{action}", target_type="change_request", target_id=cr.id,
                     target_name=cr.request_type, description=description, **kw)


def _locked(request_id: int) -> ChangeRequest:
    cr = db.session.query(ChangeRequest).filter(ChangeRequest.id == request_id).with_for_update().first()
    if cr is None:
        raise NotFound("Change request not found.")
    return cr


def submit(request_type: str, payload: dict, actor: User, reason: str | None = None,
           commit: bool = True) -> ChangeRequest:
    handler = handler_for(request_type)
    if handler.submit_permission not in permissions_for(actor):
        raise Forbidden("You do not have permission to request this change.")
    if not isinstance(payload, dict):
        raise ValidationError("payload must be an object.")
    payload = handler.validate(payload)
    amount = handler.amount(payload)
    policy = select_policy(request_type, amount)
    now = utcnow()
    cr = ChangeRequest(
        request_type=request_type, entity_type=handler.entity_type, entity_id=handler.entity_id(payload),
        payload=payload, base_version=handler.base_version(payload), amount=amount,
        branch_id=handler.branch_id(payload), status=CR_PENDING, reason=_text(reason, "reason"),
        maker_user_id=actor.id, maker_email=actor.email, submitted_at=now,
        expires_at=now + timedelta(hours=policy.expiry_hours), policy_id=policy.id,
        levels_required=len(policy.levels), levels_done=0, round=1,
    )
    db.session.add(cr)
    db.session.flush()
    _event(cr, "submit", actor, comment=cr.reason)
    _audit(cr, "SUBMITTED", handler.describe(payload), old_value=handler.old_value(payload))
    if commit:
        db.session.commit()
    return cr


def _approvals_this_level(cr: ChangeRequest) -> int:
    level = cr.levels_done + 1
    return (db.session.query(func.count(ChangeRequestEvent.id))
            .filter(ChangeRequestEvent.request_id == cr.id, ChangeRequestEvent.round == cr.round,
                    ChangeRequestEvent.action == "approve", ChangeRequestEvent.level == level).scalar())


def _already_approved(cr: ChangeRequest, actor: User) -> bool:
    return db.session.query(ChangeRequestEvent.id).filter(
        ChangeRequestEvent.request_id == cr.id, ChangeRequestEvent.round == cr.round,
        ChangeRequestEvent.action == "approve", ChangeRequestEvent.actor_user_id == actor.id).first() is not None


def _assert_decider(cr: ChangeRequest, actor: User) -> dict:
    """The actor may decide the current level. Returns that level."""
    if cr.status != CR_PENDING:
        raise Conflict(f"This change request is {cr.status}.")
    if cr.maker_user_id == actor.id:
        raise Forbidden(MAKER_MESSAGE)
    if cr.expires_at <= utcnow():
        raise Conflict("This change request has expired.")
    level = cr.policy.levels[cr.levels_done]
    assert_level_rights(level, actor, cr.amount, cr.branch_id)
    return level


def _fail_if_stale(cr: ChangeRequest, handler: Handler, actor: User) -> None:
    if cr.base_version is not None and handler.base_version(cr.payload) != cr.base_version:
        cr.status = CR_FAILED
        cr.error = STALE_MESSAGE
        cr.decided_at = utcnow()
        _event(cr, "fail", actor, comment=STALE_MESSAGE)
        _audit(cr, "FAILED", STALE_MESSAGE)
        db.session.commit()
        raise Conflict(STALE_MESSAGE)


def approve(request_id: int, actor: User, comment: str | None = None) -> ChangeRequest:
    cr = _locked(request_id)
    level = _assert_decider(cr, actor)
    if _already_approved(cr, actor):
        raise Forbidden("You have already approved this change request.")
    handler = handler_for(cr.request_type)
    _fail_if_stale(cr, handler, actor)

    _event(cr, "approve", actor, level=cr.levels_done + 1, comment=_text(comment, "comment"))
    _audit(cr, "APPROVED", f"Level {cr.levels_done + 1} of {cr.levels_required}: {handler.describe(cr.payload)}")
    if _approvals_this_level(cr) >= int(level.get("count", 1)):
        cr.levels_done += 1
    if cr.levels_done == cr.levels_required:
        # Re-validate against the current state, then apply in this transaction.
        old = handler.old_value(cr.payload)
        cr.payload = handler.validate(dict(cr.payload))
        cr.result = handler.apply(cr, actor)
        cr.status = CR_APPLIED
        cr.decided_at = cr.applied_at = utcnow()
        _event(cr, "apply", actor)
        _audit(cr, "APPLIED", handler.describe(cr.payload), old_value=old,
               new_value={"payload": cr.payload, "result": cr.result})
    db.session.commit()
    return cr


def reject(request_id: int, actor: User, comment: str | None) -> ChangeRequest:
    comment = _text(comment, "reason", required=True)
    cr = _locked(request_id)
    _assert_decider(cr, actor)
    cr.status = CR_REJECTED
    cr.decided_at = utcnow()
    _event(cr, "reject", actor, level=cr.levels_done + 1, comment=comment)
    _audit(cr, "REJECTED", comment)
    db.session.commit()
    return cr


def return_for_correction(request_id: int, actor: User, comment: str | None) -> ChangeRequest:
    comment = _text(comment, "reason", required=True)
    cr = _locked(request_id)
    _assert_decider(cr, actor)
    cr.status = CR_RETURNED
    _event(cr, "return", actor, level=cr.levels_done + 1, comment=comment)
    _audit(cr, "RETURNED", comment)
    db.session.commit()
    return cr


def resubmit(request_id: int, actor: User, payload: dict | None, reason: str | None = None) -> ChangeRequest:
    cr = _locked(request_id)
    if cr.maker_user_id != actor.id:
        raise Forbidden("Only the person who made the request can resubmit it.")
    if cr.status != CR_RETURNED:
        raise Conflict(f"Only a returned request can be resubmitted (this one is {cr.status}).")
    handler = handler_for(cr.request_type)
    old_payload = cr.payload
    new_payload = handler.validate(payload if isinstance(payload, dict) else dict(cr.payload))
    amount = handler.amount(new_payload)
    policy = select_policy(cr.request_type, amount)
    now = utcnow()
    cr.payload = new_payload
    cr.entity_id = handler.entity_id(new_payload)
    cr.base_version = handler.base_version(new_payload)
    cr.amount = amount
    cr.branch_id = handler.branch_id(new_payload)
    cr.policy_id, cr.levels_required, cr.levels_done = policy.id, len(policy.levels), 0
    cr.round += 1
    cr.status = CR_PENDING
    cr.expires_at = now + timedelta(hours=policy.expiry_hours)
    if reason is not None:
        cr.reason = _text(reason, "reason")
    db.session.flush()
    _event(cr, "resubmit", actor, comment=cr.reason)
    _audit(cr, "RESUBMITTED", handler.describe(new_payload), old_value={"payload": old_payload})
    db.session.commit()
    return cr


def cancel(request_id: int, actor: User) -> ChangeRequest:
    cr = _locked(request_id)
    if cr.maker_user_id != actor.id:
        raise Forbidden("Only the person who made the request can cancel it.")
    if cr.status not in (CR_PENDING, CR_RETURNED):
        raise Conflict(f"This change request is {cr.status}.")
    cr.status = CR_CANCELLED
    cr.decided_at = utcnow()
    _event(cr, "cancel", actor)
    _audit(cr, "CANCELLED", handler_for(cr.request_type).describe(cr.payload))
    db.session.commit()
    return cr


def expire_due(now=None) -> int:
    """Mark open requests past their expiry as expired (scheduled job)."""
    now = now or utcnow()
    due = (db.session.query(ChangeRequest)
           .filter(ChangeRequest.status.in_((CR_PENDING, CR_RETURNED)), ChangeRequest.expires_at <= now)
           .with_for_update(skip_locked=True).all())
    for cr in due:
        cr.status = CR_EXPIRED
        cr.decided_at = now
        _event(cr, "expire", None)
        _audit(cr, "EXPIRED", "Not decided before it expired.", actor_user_email="scheduler")
    db.session.commit()
    return len(due)


def can_decide(cr: ChangeRequest, actor: User) -> bool:
    try:
        _assert_decider(cr, actor)
    except (Forbidden, Conflict):
        return False
    return not _already_approved(cr, actor)


def summary(cr: ChangeRequest) -> str:
    handler = HANDLERS.get(cr.request_type)
    return handler.describe(cr.payload) if handler else cr.request_type


def inbox(actor: User, status: str | None = None, mine: bool = False):
    q = ChangeRequest.query.order_by(ChangeRequest.submitted_at.desc(), ChangeRequest.id.desc())
    if mine:
        return q.filter(ChangeRequest.maker_user_id == actor.id)
    if status:
        return q.filter(ChangeRequest.status == status)
    pending = q.filter(ChangeRequest.status == CR_PENDING).all()
    return [cr for cr in pending if can_decide(cr, actor) and in_branch_scope(actor, cr.branch_id)]


def events(cr: ChangeRequest):
    return (ChangeRequestEvent.query.filter_by(request_id=cr.id)
            .order_by(ChangeRequestEvent.at, ChangeRequestEvent.id).all())
