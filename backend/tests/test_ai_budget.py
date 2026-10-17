"""AI-12: budgets, the circuit breaker and the kill switch. Every API call is checked first.

Estimates (app/DocAI/pricing.py), claude-opus-5-5 at $4 / $20 per million tokens:
    one page: (2,500 + 2,500) × $4/M + (500 + 2,500) × $20/M = $0.02 + $0.06 = $0.080000
Actual costs of the recorded responses:
    national ID  2,950 in / 980 out    = $0.031400
    KRA PIN      3,400 in / 700 out    = $0.027600
    bank page    4,700 in / 2,100 out  = $0.060800
"""
from datetime import date
from decimal import Decimal

from app.database.database import db
from app.DocAI import pricing, service
from app.DocAI.model import AIBudgetRefusal, AIServiceState, Extraction, ExtractionCall
from app.Emails.model import OutboxEmail
from app.Settings import business
from app.Settings.model import SettingVersion
from app.utils.audit_log import AuditLog
from app.utils.dates import utcnow
from application_helpers import new_application, person, read_into
from docai_fakes import api_error, response
from test_docai import ai, client_with, read, run_jobs  # noqa: F401 (ai is a fixture)

BANK = ("bank_statement_3_pages.pdf", "application/pdf")
PAGE_ESTIMATE = Decimal("0.080000")


def set_setting(key, value, users, version_no=2, day=1):
    db.session.add(SettingVersion(key=key, value=value, effective_from=date(2026, 10, day), version_no=version_no,
                                  source="internal_decision", evidence="test", created_by=users["admin1"].email,
                                  approved_by=users["admin2"].email, approved_at=utcnow()))
    db.session.commit()
    business.clear_cache()


def again(users, ex):
    """Read the same document again (a new extraction) and run the job."""
    new = service.retry(ex.id, users["admin1"])
    run_jobs()
    return db.session.get(Extraction, new.id)


def test_ai_12_estimate_before_the_call_and_actual_cost_after(ai, staff, users):
    assert pricing.estimate_usd("claude-opus-5-5", 1) == PAGE_ESTIMATE
    p, doc = client_with(staff)
    ex = read(users, p, doc, ai, response("national_id_clean"))
    [call] = ExtractionCall.query.filter_by(extraction_id=ex.id).all()
    assert (call.estimated_cost_usd, call.cost_usd) == (PAGE_ESTIMATE, Decimal("0.031400"))
    assert ex.cost_usd == Decimal("0.031400")  # spend counts the actual cost, not the estimate


def test_ai_12_monthly_budget_counts_actual_spend_and_refuses_before_the_call(ai, staff, users, admin1):
    set_setting("ai.budget.monthly_usd", "0.12", users)
    p, doc = client_with(staff)
    first = read(users, p, doc, ai, response("national_id_clean"))               # 0 + 0.08 ≤ 0.12
    ai.queue(response("national_id_clean"))
    second = again(users, first)                                                 # 0.0314 + 0.08 ≤ 0.12 (actual)
    assert (first.status, second.status) == ("completed", "completed")
    third = again(users, second)                                                 # 0.0628 + 0.08 > 0.12
    assert third.status == "failed" and "monthly budget" in third.status_reason
    assert len(ai.calls) == 2  # the third call was never made
    refusal = AIBudgetRefusal.query.one()
    assert (refusal.kind, refusal.limit_usd, refusal.spent_usd, refusal.estimate_usd) == \
        ("monthly", Decimal("0.120000"), Decimal("0.062800"), PAGE_ESTIMATE)
    usage = admin1.get("/api/v1/ai/usage").get_json()["data"]["months"][0]
    assert [r["kind"] for r in usage["refusals"]] == ["monthly"]
    status = admin1.get("/api/v1/ai/status").get_json()["data"]
    assert status["budgets"]["monthly_usd"] == "0.12" and status["recent_refusals"][0]["label"] == "Monthly budget"


def test_ai_12_per_reading_budget_stops_a_long_statement_mid_way(ai, staff, users):
    set_setting("ai.budget.per_run_usd", "0.20", users)
    p, doc = client_with(staff, "bank_statement", BANK)
    ex = read(users, p, doc, ai, response("bank_statement_page1"), response("bank_statement_page2"))
    # page 1: 0 + 0.08; page 2: 0.0608 + 0.08; page 3: 0.1216 + 0.08 = 0.2016 > 0.20 → refused
    assert ex.status == "failed" and "per-reading budget" in ex.status_reason
    assert len(ai.calls) == 2
    refusal = AIBudgetRefusal.query.one()
    assert (refusal.kind, refusal.page_number, refusal.spent_usd) == ("per_run", 3, Decimal("0.121600"))


def test_ai_12_per_application_budget(ai, staff, users, admin1):
    set_setting("ai.budget.per_application_usd", "0.10", users)
    p = person(staff)
    app = new_application(staff, p["id"])
    first = read_into(ai, staff, admin1, app, p["id"], "national_id", "national_id_clean")   # 0 + 0.08 ≤ 0.10
    second = read_into(ai, staff, admin1, app, p["id"], "kra_pin", "kra_pin")                # 0.0314 + 0.08 > 0.10
    assert first.status == "completed"
    assert second.status == "failed" and f"Application {app['id']} has used US$0.03" in second.status_reason
    refusal = AIBudgetRefusal.query.one()
    assert (refusal.kind, refusal.application_id) == ("per_application", app["id"])
    ai.script.clear()


def test_ai_12_a_model_without_a_price_is_refused(ai, staff, users):
    set_setting("ai.model_extract", "claude-unpriced-test", users)
    p, doc = client_with(staff)
    ex = read(users, p, doc)
    assert ex.status == "failed" and "no price for claude-unpriced-test" in ex.status_reason
    assert ai.calls == [] and AIBudgetRefusal.query.one().kind == "pricing"


def test_ai_12_kill_switch_stops_queued_jobs_before_their_api_call(ai, staff, users):
    p, doc = client_with(staff)
    ex = service.request_extraction(p["id"], doc["id"], users["admin1"])  # queued while AI is on
    set_setting("ai.enabled", False, users, version_no=3, day=2)            # then switched off
    ai.queue(response("national_id_clean"))
    run_jobs()
    ex = db.session.get(Extraction, ex.id)
    assert ex.status == "failed" and "switched off" in ex.status_reason
    assert ai.calls == [] and AIBudgetRefusal.query.one().kind == "disabled"


def test_ai_12_breaker_trips_after_five_consecutive_failures_and_an_admin_resumes(ai, staff, users, admin1):
    p, doc = client_with(staff)
    ex = read(users, p, doc, ai, api_error(500), api_error(500), api_error(500))   # failures 1–3
    ai.queue(api_error(400))
    ex = again(users, ex)                                                          # 4
    assert db.session.get(AIServiceState, 1).status == "running"
    ai.queue(api_error(400))
    ex = again(users, ex)                                                          # 5 → pause
    state = db.session.get(AIServiceState, 1)
    assert state.status == "paused" and state.paused_reason == "The last 5 calls to the AI service all failed."
    alerts = OutboxEmail.query.filter_by(email_type="AI_ALERT").all()
    assert {a.recipient_email for a in alerts} == {"admin1@anchorstone.test", "admin2@anchorstone.test",
                                                    "super@anchorstone.test"}
    assert all(a.status == "queued" for a in alerts)
    assert AuditLog.query.filter_by(action="AI_PAUSED").count() == 1

    calls_before = len(ai.calls)
    ai.queue(response("national_id_clean"))
    blocked = again(users, ex)
    assert blocked.status == "failed" and "paused" in blocked.status_reason and len(ai.calls) == calls_before
    ai.script.clear()

    assert staff.post("/api/v1/ai/resume", {"reason": "fixed"}).status_code == 403
    assert admin1.post("/api/v1/ai/resume", {}).status_code == 400  # a reason is required
    res = admin1.post("/api/v1/ai/resume", {"reason": "Provider incident resolved"})
    assert res.status_code == 200 and res.get_json()["data"]["status"] == "running"
    assert admin1.post("/api/v1/ai/resume", {"reason": "again"}).status_code == 409
    resumed = AuditLog.query.filter_by(action="AI_RESUMED").one()
    assert resumed.user_email == "admin1@anchorstone.test"
    ai.queue(response("national_id_clean"))
    assert again(users, blocked).status == "completed"


def test_ai_12_breaker_trips_on_more_than_ten_failures_in_ten_minutes(ai, staff, users):
    p, doc = client_with(staff)
    ex = read(users, p, doc, ai, api_error(500), api_error(500), response("national_id_clean"))
    for _ in range(4):  # two failures, then a success: never five in a row
        ai.queue(api_error(500), api_error(500), response("national_id_clean"))
        ex = again(users, ex)
    assert db.session.get(AIServiceState, 1).status == "running"  # 10 failures: not more than 10
    ai.queue(api_error(500), response("national_id_clean"))
    ex = again(users, ex)                                         # the 11th failure pauses it
    state = db.session.get(AIServiceState, 1)
    assert state.status == "paused" and "11 calls to the AI service failed in the last 10 minutes" in state.paused_reason
    assert ex.status == "failed" and "paused" in ex.status_reason  # its retry was refused, not sent
    ai.script.clear()
