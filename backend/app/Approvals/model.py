"""
Generic maker-checker (ADR-04-1).

A change request is a proposed action plus a payload, applied by a registered
handler (app/Approvals/handlers.py) once every approval level has signed off.

    pending ──approve (all levels)──▶ applied
       │  ▲                   (stale base_version) ─▶ failed
       │  └─resubmit── returned ◀──return──┘
       ├──reject──▶ rejected
       ├──cancel (maker)──▶ cancelled
       └──(expires_at)──▶ expired

The database enforces maker ≠ checker: a trigger on change_request_events
refuses an approve / reject / return by the request's maker, and a unique
index stops one person approving twice in the same round. Events are
insert-only.

Approval policies pick the levels by request type and amount; each level names
the permission an approver needs and how many distinct approvers it takes.
"""
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.database.database import db
from app.utils.dates import iso
from app.utils.money import as_str
from base_model import Base

CR_PENDING = "pending"
CR_RETURNED = "returned"
CR_APPLIED = "applied"
CR_REJECTED = "rejected"
CR_CANCELLED = "cancelled"
CR_EXPIRED = "expired"
CR_FAILED = "failed"
CR_STATUSES = (CR_PENDING, CR_RETURNED, CR_APPLIED, CR_REJECTED, CR_CANCELLED, CR_EXPIRED, CR_FAILED)
CR_OPEN = (CR_PENDING, CR_RETURNED)

EVENT_ACTIONS = ("submit", "approve", "reject", "return", "resubmit", "cancel", "apply", "expire", "fail")


class ApprovalPolicy(Base, db.Model):
    __tablename__ = "approval_policies"
    __table_args__ = (
        CheckConstraint("min_amount IS NULL OR max_amount IS NULL OR min_amount <= max_amount",
                        name="ck_approval_policies_amount_band"),
        CheckConstraint("jsonb_typeof(levels) = 'array' AND jsonb_array_length(levels) >= 1",
                        name="ck_approval_policies_levels"),
        CheckConstraint("expiry_hours > 0", name="ck_approval_policies_expiry"),
    )

    id = Column(Integer, primary_key=True)
    request_type = Column(String(60), nullable=False, index=True)
    min_amount = Column(Numeric(20, 2), nullable=True)  # inclusive; NULL = no lower bound
    max_amount = Column(Numeric(20, 2), nullable=True)  # inclusive; NULL = no upper bound
    # [{"permission": "role.manage", "count": 1}, ...] — one entry per level, in order.
    levels = Column(JSONB, nullable=False)
    same_branch_required = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    expiry_hours = Column(Integer, nullable=False, default=168, server_default="168")
    active = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    description = Column(Text, nullable=True)

    def to_dict(self) -> dict:
        return {"id": self.id, "request_type": self.request_type, "min_amount": as_str(self.min_amount),
                "max_amount": as_str(self.max_amount), "levels": self.levels,
                "same_branch_required": self.same_branch_required, "expiry_hours": self.expiry_hours}


class ChangeRequest(Base, db.Model):
    __tablename__ = "change_requests"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'returned', 'applied', 'rejected', 'cancelled', 'expired', 'failed')",
            name="ck_change_requests_status",
        ),
        CheckConstraint("currency = 'KES'", name="ck_change_requests_currency_kes"),
        CheckConstraint("amount IS NULL OR amount >= 0", name="ck_change_requests_amount"),
        CheckConstraint("levels_done >= 0 AND levels_done <= levels_required", name="ck_change_requests_levels"),
        Index("ix_change_requests_status_type", "status", "request_type"),
    )

    id = Column(Integer, primary_key=True)
    request_type = Column(String(60), nullable=False)
    entity_type = Column(String(50), nullable=True)
    entity_id = Column(String(64), nullable=True)  # NULL for creations
    payload = Column(JSONB, nullable=False)
    # The target's state when the request was made; approval refuses if it moved.
    base_version = Column(String(128), nullable=True)
    amount = Column(Numeric(20, 2), nullable=True)
    currency = Column(String(3), nullable=False, default="KES", server_default="KES")
    branch_id = Column(Integer, ForeignKey("branches.id", ondelete="RESTRICT"), nullable=True)
    status = Column(String(10), nullable=False, default=CR_PENDING, server_default=CR_PENDING)
    reason = Column(Text, nullable=True)

    maker_user_id = Column(Integer, ForeignKey("user.id", ondelete="RESTRICT"), nullable=False, index=True)
    maker_email = Column(String(120), nullable=False)
    submitted_at = Column(DateTime(timezone=True), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    decided_at = Column(DateTime(timezone=True), nullable=True)
    applied_at = Column(DateTime(timezone=True), nullable=True)

    policy_id = Column(Integer, ForeignKey("approval_policies.id", ondelete="RESTRICT"), nullable=False)
    levels_required = Column(Integer, nullable=False)
    levels_done = Column(Integer, nullable=False, default=0, server_default="0")
    round = Column(Integer, nullable=False, default=1, server_default="1")  # bumps on resubmit

    result = Column(JSONB, nullable=True)
    error = Column(Text, nullable=True)

    policy = db.relationship("ApprovalPolicy")

    def to_dict(self, summary: str | None = None) -> dict:
        return {
            "id": self.id, "request_type": self.request_type, "entity_type": self.entity_type,
            "entity_id": self.entity_id, "payload": self.payload, "summary": summary,
            "amount": as_str(self.amount), "currency": self.currency, "branch_id": self.branch_id,
            "status": self.status, "reason": self.reason, "maker_email": self.maker_email,
            "submitted_at": iso(self.submitted_at), "expires_at": iso(self.expires_at),
            "decided_at": iso(self.decided_at), "applied_at": iso(self.applied_at),
            "levels_required": self.levels_required, "levels_done": self.levels_done, "round": self.round,
            "levels": self.policy.levels if self.policy else None, "result": self.result, "error": self.error,
        }


class ChangeRequestEvent(Base, db.Model):
    __tablename__ = "change_request_events"
    __table_args__ = (
        CheckConstraint(
            "action IN ('submit', 'approve', 'reject', 'return', 'resubmit', 'cancel', 'apply', 'expire', 'fail')",
            name="ck_change_request_events_action",
        ),
        # Nobody approves the same request twice in one round (across levels too).
        Index("uq_change_request_events_one_approval", "request_id", "round", "actor_user_id",
              unique=True, postgresql_where=text("action = 'approve'")),
    )

    id = Column(Integer, primary_key=True)
    request_id = Column(Integer, ForeignKey("change_requests.id", ondelete="RESTRICT"), nullable=False, index=True)
    round = Column(Integer, nullable=False)
    action = Column(String(10), nullable=False)
    level = Column(Integer, nullable=True)
    actor_user_id = Column(Integer, ForeignKey("user.id", ondelete="RESTRICT"), nullable=True)  # NULL = system
    actor_email = Column(String(120), nullable=False)
    comment = Column(Text, nullable=True)
    at = Column(DateTime(timezone=True), nullable=False)

    def to_dict(self) -> dict:
        return {"id": self.id, "round": self.round, "action": self.action, "level": self.level,
                "actor_email": self.actor_email, "comment": self.comment, "at": iso(self.at)}
