"""
The one implementation of the approval rules, used by change requests and by
the domain records that keep their own status (withdrawals, interest periods).

    maker ≠ checker      compared case-insensitively on email (and by user id
                         in the database for change requests)
    policy               chosen by request type and amount
    permission           the level's permission
    limit                the approver's transaction limit must cover the amount
    branch               the record's branch must be in the approver's scope
"""
from decimal import Decimal

from sqlalchemy import and_, func, or_

from app.Access.service import in_branch_scope, limit_for, permissions_for
from app.Admin.model import User
from app.Approvals.model import ApprovalPolicy
from app.database.database import db
from app.utils.http import Forbidden, ValidationError
from app.utils.money import fmt_kes


def assert_maker_is_not_checker(maker_email: str, actor_email: str, message: str) -> None:
    if (maker_email or "").strip().lower() == (actor_email or "").strip().lower():
        raise Forbidden(message)


def select_policy(request_type: str, amount: Decimal | None) -> ApprovalPolicy:
    q = ApprovalPolicy.query.filter(ApprovalPolicy.request_type == request_type, ApprovalPolicy.active.is_(True))
    if amount is not None:
        q = q.filter(or_(ApprovalPolicy.min_amount.is_(None), ApprovalPolicy.min_amount <= amount),
                     or_(ApprovalPolicy.max_amount.is_(None), ApprovalPolicy.max_amount >= amount))
    else:
        q = q.filter(and_(ApprovalPolicy.min_amount.is_(None), ApprovalPolicy.max_amount.is_(None)))
    policies = q.order_by(ApprovalPolicy.min_amount.desc().nullslast(), ApprovalPolicy.id).all()
    if not policies:
        raise ValidationError(f"No approval policy covers {request_type}"
                              + (f" for {fmt_kes(amount)}." if amount is not None else "."))
    return policies[0]


def user_by_email(email: str) -> User:
    user = User.query.filter(func.lower(User.email) == (email or "").strip().lower()).first()
    if user is None:
        raise Forbidden("Unknown approver.")
    return user


def assert_level_rights(level: dict, actor: User, amount: Decimal | None, branch_id: int | None) -> None:
    """The actor holds the level's permission, a limit covering the amount, and the branch."""
    permission = level["permission"]
    if permission not in permissions_for(actor):
        raise Forbidden("You do not have permission to approve this.")
    if amount is not None:
        limit = limit_for(actor, permission)
        if not limit.allows(Decimal(amount)):
            cap = "no approval limit" if not limit.configured else f"a limit of {fmt_kes(limit.max_per_item)}"
            raise Forbidden(f"{fmt_kes(amount)} is above your approval limit (you have {cap}). "
                            "It needs an approver with a higher limit.")
    if not in_branch_scope(actor, branch_id):
        raise Forbidden("This record belongs to a branch outside your access.")


def assert_can_decide(request_type: str, *, maker_email: str, actor_email: str, amount: Decimal | None,
                      branch_id: int | None, maker_message: str) -> None:
    """
    For domain records that keep their own status (one approval level).
    Maker-checker is checked first, with the record's own message.
    """
    assert_maker_is_not_checker(maker_email, actor_email, maker_message)
    policy = select_policy(request_type, amount)
    if len(policy.levels) != 1 or int(policy.levels[0].get("count", 1)) != 1:
        raise ValidationError(f"{request_type} needs multi-level approval, which this record doesn't support yet.")
    assert_level_rights(policy.levels[0], user_by_email(actor_email), amount, branch_id)
