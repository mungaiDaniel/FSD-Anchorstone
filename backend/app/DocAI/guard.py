"""
Spending limits, the circuit breaker and the kill switch (AI-12). Checked by the
extractor before EVERY API call (retries and repair calls too), so a queued job is
stopped as surely as a new request.

Before a call (check_before_call), in this order:
    kill switch      ai.enabled is false (re-read now, not cached)  → refused
    breaker          the AI service is paused                       → refused
    price            the model has no price in ai.price_table       → refused
    per reading      this reading's ACTUAL spend + the estimate > ai.budget.per_run_usd
    per application  for every application holding the document: its readings' spend + the
                     estimate > ai.budget.per_application_usd
    monthly          this Nairobi month's spend + the estimate > ai.budget.monthly_usd
A refusal is recorded (ai_budget_refusals, shown on the AI usage page) and the reading
ends "extraction failed" with the reason. Spend is always the ACTUAL cost of past calls
(from the token usage the API returned), never their estimates.

After a call (after_call): when the last ai.breaker.consecutive_failures calls all failed,
or more than ai.breaker.window_failures calls failed in the last ai.breaker.window_minutes,
the service is paused and every admin is alerted through the outbox. Only an admin
resumes it (resume(), audited).
"""
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import func

from app.Admin.model import User
from app.database.database import db
from app.DocAI import pricing
from app.DocAI.model import AIBudgetRefusal, AIServiceState, Extraction, ExtractionCall
from app.Documents.model import DocumentLink
from app.Emails.model import STATUS_QUEUED, OutboxEmail
from app.Settings import business
from app.utils.audit_log import create_audit_log
from app.utils.dates import EAT, today_eat, utcnow
from app.utils.http import Conflict, ValidationError

FAILED = ("retryable_error", "permanent_error")
EMAIL_AI_ALERT = "AI_ALERT"


class Refused(Exception):
    pass


def state() -> AIServiceState:
    row = db.session.get(AIServiceState, 1)
    if row is None:  # seeded by the migration; recreated if ever missing
        row = AIServiceState(id=1, status="running")
        db.session.add(row)
        db.session.flush()
    return row


def _money(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


def month_start_utc() -> datetime:
    today = today_eat()
    return datetime(today.year, today.month, 1, tzinfo=EAT)


def spent_this_month() -> Decimal:
    total = (db.session.query(func.coalesce(func.sum(ExtractionCall.cost_usd), 0))
             .filter(ExtractionCall.started_at >= month_start_utc()).scalar())
    return Decimal(total)


def _application_ids(document_id) -> list[int]:
    return sorted(int(l.entity_id) for l in DocumentLink.query.filter_by(document_id=document_id,
                                                                         entity_type="loan_application"))


def spent_on_application(application_id: int) -> Decimal:
    docs = [l.document_id for l in DocumentLink.query.filter_by(entity_type="loan_application",
                                                                entity_id=str(application_id))]
    if not docs:
        return Decimal("0")
    total = (db.session.query(func.coalesce(func.sum(ExtractionCall.cost_usd), 0))
             .join(Extraction, Extraction.id == ExtractionCall.extraction_id)
             .filter(Extraction.document_id.in_(docs)).scalar())
    return Decimal(total)


def _spent_on_reading(extraction_id: int) -> Decimal:
    total = (db.session.query(func.coalesce(func.sum(ExtractionCall.cost_usd), 0))
             .filter(ExtractionCall.extraction_id == extraction_id).scalar())
    return Decimal(total)


def _refuse(ex: Extraction, kind: str, message: str, page: int | None, *, limit=None, spent=None, estimate=None,
            application_id: int | None = None):
    db.session.add(AIBudgetRefusal(extraction_id=ex.id, application_id=application_id, page_number=page, kind=kind,
                                   limit_usd=limit, spent_usd=spent, estimate_usd=estimate, message=message,
                                   refused_at=utcnow()))
    db.session.commit()
    raise Refused(message)


def check_before_call(ex: Extraction, pages: int, page_number: int | None = None) -> Decimal:
    """The estimated cost of the call, or Refused (recorded) when it may not be made."""
    business.clear_cache()  # a kill switch or a new budget applies to queued jobs at once
    if not business.get("ai.enabled"):
        _refuse(ex, "disabled", "Automatic document reading was switched off (ai.enabled) before this call. "
                                "Capture the details by hand, or retry once it is on again.", page_number)
    if state().status == "paused":
        _refuse(ex, "paused", "AI reading is paused after repeated service failures (circuit breaker). Retry once "
                              "an admin resumes it, or capture the details by hand.", page_number)
    estimate = pricing.estimate_usd(ex.model_requested, pages)
    if estimate is None:
        _refuse(ex, "pricing", f"There is no price for {ex.model_requested} in ai.price_table, so the call can't "
                               "be checked against the budgets.", page_number)
    limit = Decimal(business.get("ai.budget.per_run_usd"))
    spent = _spent_on_reading(ex.id)
    if spent + estimate > limit:
        _refuse(ex, "per_run", f"This reading has used US${_money(spent)} and the next call would take it past the "
                               f"US${_money(limit)} per-reading budget (ai.budget.per_run_usd).", page_number,
                limit=limit, spent=spent, estimate=estimate)
    limit = Decimal(business.get("ai.budget.per_application_usd"))
    for app_id in _application_ids(ex.document_id):
        spent = spent_on_application(app_id)
        if spent + estimate > limit:
            _refuse(ex, "per_application", f"Application {app_id} has used US${_money(spent)} of its "
                                           f"US${_money(limit)} AI budget (ai.budget.per_application_usd).",
                    page_number, limit=limit, spent=spent, estimate=estimate, application_id=app_id)
    limit = Decimal(business.get("ai.budget.monthly_usd"))
    spent = spent_this_month()
    if spent + estimate > limit:
        _refuse(ex, "monthly", f"This month's AI spend is US${_money(spent)}; the next call would pass the "
                               f"US${_money(limit)} monthly budget (ai.budget.monthly_usd).", page_number,
                limit=limit, spent=spent, estimate=estimate)
    return estimate


def _admins() -> list[User]:
    return (User.query.filter(User.role.in_(("admin", "super_admin")), User.status == "active")
            .order_by(User.email).all())


def _alert(reason: str) -> None:
    body = ("Hello,\n\n"
            "Automatic document reading has been PAUSED by the circuit breaker.\n\n"
            "WHY\n\n"
            f"• {reason}\n\n"
            "Readings already queued will stop before calling the AI service and show \"extraction failed\". "
            "Staff can capture details by hand meanwhile.\n\n"
            "Check the AI usage page, then resume AI reading there once the service is healthy (an admin action, "
            "recorded in the audit log).\n\n"
            "Anchorstone Capital Ltd — Statement System")
    for user in _admins():
        db.session.add(OutboxEmail(email_type=EMAIL_AI_ALERT, investor_id=None, recipient_email=user.email,
                                   recipient_name=user.name, subject="AI document reading paused",
                                   body=body, status=STATUS_QUEUED, created_by="scheduler"))


def after_call(outcome: str) -> None:
    """Trip the breaker on repeated failures (called after every recorded call)."""
    if outcome not in FAILED:
        return
    consecutive = int(business.get("ai.breaker.consecutive_failures"))
    window_failures = int(business.get("ai.breaker.window_failures"))
    window = timedelta(minutes=int(business.get("ai.breaker.window_minutes")))
    last = [c.outcome for c in ExtractionCall.query.order_by(ExtractionCall.finished_at.desc(),
                                                              ExtractionCall.started_at.desc()).limit(consecutive)]
    reason = None
    if len(last) == consecutive and all(o in FAILED for o in last):
        reason = f"The last {consecutive} calls to the AI service all failed."
    else:
        recent = ExtractionCall.query.filter(ExtractionCall.outcome.in_(FAILED),
                                             ExtractionCall.finished_at >= utcnow() - window).count()
        if recent > window_failures:
            reason = f"{recent} calls to the AI service failed in the last {int(window.total_seconds() // 60)} minutes."
    if reason is None:
        return
    row = db.session.query(AIServiceState).filter_by(id=1).with_for_update().one()
    if row.status == "paused":
        db.session.commit()
        return
    old = row.to_dict()
    row.status, row.paused_at, row.paused_reason = "paused", utcnow(), reason
    _alert(reason)
    create_audit_log("AI_PAUSED", target_type="ai_service", target_id=1, target_name="AI document reading",
                     description=reason, old_value=old, new_value=row.to_dict(), actor_user_email="scheduler",
                     actor_user_name="Circuit breaker")
    db.session.commit()


def resume(actor, reason: str | None) -> AIServiceState:
    reason = " ".join(str(reason or "").split())
    if not reason:
        raise ValidationError("Say why it is safe to resume (e.g. the provider's incident is resolved).")
    row = db.session.query(AIServiceState).filter_by(id=1).with_for_update().one()
    if row.status != "paused":
        raise Conflict("AI reading isn't paused.")
    old = row.to_dict()
    row.status, row.resumed_at, row.resumed_by, row.resume_reason = "running", utcnow(), actor.email, reason
    create_audit_log("AI_RESUMED", target_type="ai_service", target_id=1, target_name="AI document reading",
                     description=reason, old_value=old, new_value=row.to_dict())
    db.session.commit()
    return row


def status() -> dict:
    business.clear_cache()
    return {**state().to_dict(), "enabled": bool(business.get("ai.enabled")),
            "budgets": {"monthly_usd": str(business.get("ai.budget.monthly_usd")),
                        "per_application_usd": str(business.get("ai.budget.per_application_usd")),
                        "per_run_usd": str(business.get("ai.budget.per_run_usd"))},
            "spent_this_month_usd": str(spent_this_month().quantize(Decimal("0.000001"))),
            "breaker": {"consecutive_failures": business.get("ai.breaker.consecutive_failures"),
                        "window_failures": business.get("ai.breaker.window_failures"),
                        "window_minutes": business.get("ai.breaker.window_minutes")},
            "recent_refusals": [r.to_dict() for r in AIBudgetRefusal.query.order_by(
                AIBudgetRefusal.refused_at.desc(), AIBudgetRefusal.id.desc()).limit(50)]}
