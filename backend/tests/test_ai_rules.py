"""Phase 3b: pre-selection rules (AI-08), fairness (AI-11) and the human decision (AI-09)."""
import copy
from pathlib import Path

import pytest
from sqlalchemy import text

from app.Applications import screening
from app.Applications.model import CreditDecision, ScreeningRuleResult, ScreeningRun
from app.Applications.ruleset import DEFAULT_RULE_SET
from app.database.database import db
from app.Settings import business
from app.utils.dates import utcnow
from application_helpers import new_application, person, read_into, review_and_approve
from test_docai import ai  # noqa: F401 (fixture)

BACKEND = Path(__file__).resolve().parents[1]


def inputs(party_type="person", product="business_loan", **values):
    """Hand-made inputs: every metric passing unless overridden; None = missing."""
    base = {"months_in_business": 36, "avg_monthly_inflow_6m": "200000.00", "estimated_instalment": "45840.00",
            "crb_status": "clear", "forced_sale_cover_percent": "200.00", "age_at_maturity": 40,
            "identity_consistent": "pass", "cr12_directors_match": "pass", "returned_items_6m": 0,
            "lender_repayment_share_6m": "0.1000", "amount_requested": "500000.00", "term_months": 12}
    base.update(values)
    metrics = {k: ({"value": v, "missing": None, "sources": []} if v is not None else
                   {"value": None, "missing": f"no {k.replace('_', ' ')}", "sources": []}) for k, v in base.items()}
    return {"as_of": "2026-10-05", "application": {"id": 1, "application_no": "AP-0000001", "party_type": party_type,
                                                  "product_code": product}, "metrics": metrics, "checks": []}


def by_rule(results):
    return {r["rule_id"]: r for r in results}


# ── The rule set is data (AI-08) ──


def test_ai_08_rule_set_v1_is_the_nine_wa10_rules_stored_as_a_setting():
    row = business.current_version("screening.rule_set")
    assert row.version_no == 1 and row.value == DEFAULT_RULE_SET
    assert [r["id"] for r in row.value["rules"]] == [f"R{i}" for i in range(1, 10)]
    descriptions = [r["description"] for r in row.value["rules"]]
    assert descriptions[2] == "CRB: listed → Not qualified; cleared → Needs review"
    assert {r["metric"]: r["outcome_if_failed"] for r in row.value["rules"]}["months_in_business"] == "not_qualified"


@pytest.mark.parametrize("change, outcome, failing", [
    ({}, "shortlisted", []),
    ({"months_in_business": 6}, "not_qualified", ["R1"]),
    ({"avg_monthly_inflow_6m": "137519.99"}, "needs_review", ["R2"]),        # 3 × 45,840.00 = 137,520.00
    ({"avg_monthly_inflow_6m": "137520.00"}, "shortlisted", []),
    ({"crb_status": "listed"}, "not_qualified", ["R3"]),
    ({"crb_status": "previously_listed_cleared"}, "needs_review", ["R3"]),
    ({"forced_sale_cover_percent": "124.99"}, "needs_review", ["R4"]),
    ({"age_at_maturity": 71}, "not_qualified", ["R5"]),
    ({"age_at_maturity": 17}, "not_qualified", ["R5"]),
    ({"identity_consistent": "needs_review"}, "needs_review", ["R6"]),
    ({"returned_items_6m": 3}, "needs_review", ["R8"]),
    ({"lender_repayment_share_6m": "0.5000"}, "needs_review", ["R9"]),
    ({"months_in_business": 6, "returned_items_6m": 5}, "not_qualified", ["R1", "R8"]),
])
def test_ai_08_outcome_logic(change, outcome, failing):
    got, results = screening.evaluate(DEFAULT_RULE_SET, inputs(**change))
    assert got == outcome
    assert sorted(r["rule_id"] for r in results if r["result"] == "fail") == failing
    assert by_rule(results)["R7"]["result"] == "not_applicable"  # an individual: no CR12


def test_ai_08_missing_input_is_needs_review_with_missing_data_never_a_pass():
    got, results = screening.evaluate(DEFAULT_RULE_SET, inputs(avg_monthly_inflow_6m=None))
    r2 = by_rule(results)["R2"]
    assert got == "needs_review" and r2["result"] == "missing"
    assert r2["reason"] == "Missing data: no avg monthly inflow 6m."
    got, results = screening.evaluate(DEFAULT_RULE_SET, inputs(estimated_instalment=None))  # the multiplier's input
    assert by_rule(results)["R2"]["result"] == "missing"
    # Missing data never outweighs a Not qualified failure, and never passes.
    got, _ = screening.evaluate(DEFAULT_RULE_SET, inputs(crb_status=None, months_in_business=1))
    assert got == "not_qualified"


def test_ai_08_rules_that_dont_apply_are_not_applicable_and_dont_count():
    got, results = screening.evaluate(DEFAULT_RULE_SET, inputs(party_type="organisation", product="bridge_loan",
                                                               age_at_maturity=None, forced_sale_cover_percent=None))
    assert got == "shortlisted"
    assert by_rule(results)["R4"]["result"] == by_rule(results)["R5"]["result"] == "not_applicable"
    assert by_rule(results)["R7"]["result"] == "pass"


def test_ai_08_evaluation_is_deterministic():
    data = inputs(returned_items_6m=3)
    first = screening.evaluate(DEFAULT_RULE_SET, data)
    for _ in range(5):
        assert screening.evaluate(copy.deepcopy(DEFAULT_RULE_SET), copy.deepcopy(data)) == first
    assert screening.inputs_hash(data) == screening.inputs_hash(copy.deepcopy(data))


# ── From confirmed data to a stored run ──


def _screened_application(ai, staff, admin1, admin2, **app_overrides):
    p = person(staff)
    app = new_application(staff, p["id"], business_start_date="2020-01-15", **app_overrides)
    for doc_type, name in (("national_id", "national_id_clean"), ("kra_pin", "kra_pin"),
                           ("valuation_report", "valuation_report")):
        ex = read_into(ai, staff, admin1, app, p["id"], doc_type, name)
        review_and_approve(admin1, admin2, ex.id, application_id=app["id"])
    ex = read_into(ai, staff, admin1, app, p["id"], "bank_statement", "bank_statement_page1",
                   "bank_statement_page2", "bank_statement_page3")
    review_and_approve(admin1, admin2, ex.id, application_id=app["id"])
    return p, app


def test_ai_08_screening_uses_confirmed_data_and_records_the_rule_set_version(ai, staff, admin1, admin2):
    p, app = _screened_application(ai, staff, admin1, admin2)
    crb = admin1.post(f"/api/v1/applications/{app['id']}/crb",
                      {"status": "clear", "status_date": "2026-09-30", "bureau": "Sample Bureau"}).get_json()["data"]
    admin2.post(f"/api/v1/change-requests/{crb['change_request_id']}/approve")
    res = staff.post(f"/api/v1/applications/{app['id']}/screen")
    assert res.status_code == 201, res.get_json()
    run = res.get_json()["data"]
    rules = by_rule(run["rules"])
    assert (run["rule_set_version_no"], run["recommendation_only"]) == (1, True)
    assert rules["R1"]["result"] == "pass" and rules["R1"]["value"] == 80          # 2020-01-15 → 2026-10-05
    assert rules["R3"]["result"] == "pass"
    assert rules["R4"]["value"] == "975.00"                                         # 4,875,000 ÷ 500,000
    assert rules["R5"]["value"] == 37                                               # born 1990-01-01, matures 2027-10-05
    assert rules["R6"]["result"] == "pass"
    for rule_id in ("R2", "R8", "R9"):  # the sample statement covers July–September only
        assert rules[rule_id]["result"] == "missing"
        assert rules[rule_id]["reason"] == "Missing data: approved statements cover 3 of the last 6 months."
    assert rules["R7"]["result"] == "not_applicable"
    assert run["outcome"] == "needs_review"
    assert len(run["inputs_sha256"]) == 64

    # The stored run re-evaluates to exactly what was stored (deterministic, reproducible).
    stored = db.session.get(ScreeningRun, run["id"])
    outcome, results = screening.evaluate(stored.rule_set, stored.inputs)
    assert outcome == stored.outcome
    assert [r.to_dict() for r in ScreeningRuleResult.query.filter_by(run_id=stored.id)
            .order_by(ScreeningRuleResult.position)] == results
    assert screening.inputs_hash(stored.inputs) == stored.inputs_sha256
    again = staff.post(f"/api/v1/applications/{app['id']}/screen").get_json()["data"]
    assert (again["inputs_sha256"], again["outcome"], again["rules"]) == (run["inputs_sha256"], run["outcome"],
                                                                         run["rules"])
    for sql in ("UPDATE screening_runs SET outcome = 'shortlisted'", "DELETE FROM screening_rule_results"):
        with pytest.raises(Exception, match="insert-only"):
            db.session.execute(text(sql))
        db.session.rollback()


def test_ai_08_changing_the_rules_is_a_new_version_under_maker_checker(staff, admin1, admin2, superadmin):
    p = person(staff, consented=False)
    app = new_application(staff, p["id"])
    first = staff.post(f"/api/v1/applications/{app['id']}/screen").get_json()["data"]
    changed = copy.deepcopy(DEFAULT_RULE_SET)
    changed["rules"][7]["threshold"] = 1  # bounced items at most 1
    res = admin1.post("/api/v1/settings/business/screening.rule_set",
                      {"value": changed, "source": "client_confirmed", "evidence": "Credit committee minute 12"})
    assert res.status_code == 201, res.get_json()
    cr_id = res.get_json()["data"]["id"]
    assert admin1.post(f"/api/v1/change-requests/{cr_id}/approve").status_code == 403  # maker ≠ checker
    assert business.current_version("screening.rule_set").version_no == 1  # nothing until approved
    assert admin2.post(f"/api/v1/change-requests/{cr_id}/approve").status_code == 200
    business.clear_cache()
    second = staff.post(f"/api/v1/applications/{app['id']}/screen").get_json()["data"]
    assert (first["rule_set_version_no"], second["rule_set_version_no"]) == (1, 2)
    assert by_rule(second["rules"])["R8"]["threshold"] == 1
    assert db.session.get(ScreeningRun, first["id"]).rule_set["rules"][7]["threshold"] == 2  # old run kept


# ── Fairness (AI-11) ──


@pytest.mark.parametrize("rule, message", [
    ({"metric": "gender", "comparison": "==", "threshold": "M"}, "gender is a protected attribute"),
    ({"metric": "marital_status", "comparison": "==", "threshold": "single"}, "protected attribute"),
    ({"metric": "religion", "comparison": "!=", "threshold": "x"}, "protected attribute"),
    ({"metric": "credit_score_from_ai", "comparison": ">=", "threshold": 1}, "unknown metric"),
    ({"metric": "months_in_business", "comparison": ">=", "threshold": 12, "outcome_if_failed": "approved"},
     "can never approve"),
    ({"metric": "crb_status", "comparison": ">=", "threshold": "clear"}, "is text"),
])
def test_ai_11_protected_attributes_and_unknown_metrics_cannot_be_used(admin1, rule, message):
    bad = copy.deepcopy(DEFAULT_RULE_SET)
    bad["rules"].append({"id": "R10", "description": "Bad rule", "outcome_if_failed": "needs_review", **rule})
    res = admin1.post("/api/v1/settings/business/screening.rule_set",
                      {"value": bad, "source": "internal_decision", "evidence": "test"})
    assert res.status_code == 400 and message in res.get_json()["message"]


def test_ai_11_no_rule_can_read_a_protected_attribute():
    from app.Applications.ruleset import METRICS, PROTECTED
    assert not set(METRICS) & set(PROTECTED)
    source = (BACKEND / "app" / "Applications" / "screening.py").read_text(encoding="utf-8")
    for column in ("gender", "marital_status", "religion", "ethnicity"):
        assert column not in source


# ── People decide (AI-09) ──


def _run(app_id, outcome, by="staff@anchorstone.test"):
    version = business.current_version("screening.rule_set")
    run = ScreeningRun(application_id=app_id, rule_set_version_id=version.id, rule_set_version_no=version.version_no,
                       rule_set=version.value, inputs={}, inputs_sha256="0" * 64, outcome=outcome, evaluated_by=by,
                       evaluated_at=utcnow())
    db.session.add(run)
    db.session.commit()
    return run


def test_ai_09_a_person_decides_with_a_reason_and_the_system_never_declines(staff, admin1):
    p = person(staff, consented=False)
    app = new_application(staff, p["id"])
    url = f"/api/v1/applications/{app['id']}/decision"
    assert admin1.post(url, {"decision": "decline", "reason": "x"}).status_code == 400  # no run yet
    staff.post(f"/api/v1/applications/{app['id']}/screen")
    assert CreditDecision.query.count() == 0  # screening alone never decides
    assert staff.post(url, {"decision": "decline", "reason": "Too risky"}).status_code == 403  # no credit.decide
    assert admin1.post(url, {"decision": "decline"}).status_code == 400  # reason is mandatory
    assert admin1.post(url, {"decision": "reject", "reason": "x"}).status_code == 400
    res = admin1.post(url, {"decision": "more_info", "reason": "Need six months of statements"})
    assert res.status_code == 201 and res.get_json()["data"]["decision"]["decision"] == "more_info"
    res = admin1.post(url, {"decision": "decline", "reason": "Existing lender arrears"})
    assert res.status_code == 201
    assert staff.get(f"/api/v1/applications/{app['id']}").get_json()["data"]["status"] == "decided"
    assert admin1.post(url, {"decision": "proceed", "reason": "x"}).status_code == 409
    for sql in ("UPDATE credit_decisions SET reason = 'edited'", "DELETE FROM credit_decisions"):
        with pytest.raises(Exception, match="insert-only"):
            db.session.execute(text(sql))
        db.session.rollback()


def test_ai_09_proceeding_against_not_qualified_needs_a_second_approver(staff, admin1, admin2):
    p = person(staff, consented=False)
    app = new_application(staff, p["id"])
    run = _run(app["id"], "not_qualified")
    url = f"/api/v1/applications/{app['id']}/decision"
    res = admin1.post(url, {"decision": "proceed", "reason": "Listing was a disputed telco debt, since cleared"})
    assert res.status_code == 202 and res.get_json()["data"]["status"] == "pending_approval"
    cr_id = res.get_json()["data"]["change_request_id"]
    assert CreditDecision.query.count() == 0
    assert admin1.post(url, {"decision": "proceed", "reason": "again"}).status_code == 409  # one at a time
    assert admin1.post(f"/api/v1/change-requests/{cr_id}/approve").status_code == 403    # maker ≠ checker
    assert admin2.post(f"/api/v1/change-requests/{cr_id}/approve").status_code == 200
    d = CreditDecision.query.one()
    assert (d.decision, d.override, d.decided_by, d.approved_by, d.run_id) == \
        ("proceed", True, "admin1@anchorstone.test", "admin2@anchorstone.test", run.id)
    # The database refuses an override without a different approver.
    with pytest.raises(Exception, match="ck_credit_decisions"):
        db.session.execute(text("INSERT INTO credit_decisions (application_id, run_id, decision, reason, override, "
                                "decided_by, decided_at, approved_by, date_created, date_updated) VALUES "
                                "(:a, :r, 'proceed', 'x', true, 'a@x', now(), 'A@x', now(), now())"),
                           {"a": app["id"], "r": run.id})
    db.session.rollback()


def test_ai_09_shortlisted_applications_queue_for_credit_analysis(staff, admin1):
    p = person(staff, consented=False)
    shortlisted = new_application(staff, p["id"])
    review = new_application(staff, p["id"])
    declined = new_application(staff, p["id"])
    _run(shortlisted["id"], "shortlisted")
    _run(review["id"], "needs_review")
    _run(declined["id"], "shortlisted")
    admin1.post(f"/api/v1/applications/{declined['id']}/decision", {"decision": "decline", "reason": "Withdrawn"})
    queue = staff.get("/api/v1/applications?queue=ready_for_credit").get_json()["data"]["items"]
    assert [a["application_no"] for a in queue] == [shortlisted["application_no"]]
    assert queue[0]["recommendation"] == "shortlisted"
