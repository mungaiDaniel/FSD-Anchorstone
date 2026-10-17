"""Phase 3b end to end, and the oversight views (AI-10 traceability, AI-12 cost, AI-13 accuracy).

applicant → consent → upload sample documents → AI reads them (recorded responses) →
staff review and a second person approves → CRB status confirmed → pre-selection →
a person records the decision → the decision log shows the whole trace.
"""
from app.Applications.model import CreditDecision, ScreeningRun
from app.database.database import db
from app.Documents.model import DataAccessLog
from app.utils.audit_log import AuditLog
from application_helpers import new_application, person, read_into, review_and_approve
from test_docai import ai  # noqa: F401 (fixture)


def test_ai_end_to_end_applicant_to_decision_with_the_full_trace_stored(ai, staff, admin1, admin2):
    # Applicant with consent (person() records it), application, documents read by the (fake) AI.
    p = person(staff)
    app = new_application(staff, p["id"], business_start_date="2019-03-01")
    readings = {}
    for doc_type, recorded in (("national_id", ["national_id_clean"]), ("kra_pin", ["kra_pin"]),
                               ("valuation_report", ["valuation_report"]), ("crb_report", ["crb_report"]),
                               ("bank_statement", ["bank_statement_page1", "bank_statement_page2_misread",
                                                   "bank_statement_page3"])):
        readings[doc_type] = read_into(ai, staff, admin1, app, p["id"], doc_type, *recorded)
    assert readings["bank_statement"].status == "needs_review"  # page 2 misread, caught in Python

    # Review: one value corrected (beside the AI value), the misread row fixed; a second person approves.
    review_and_approve(admin1, admin2, readings["national_id"].id,
                       corrections={"serial_number": "000000002"}, application_id=app["id"])
    for doc_type in ("kra_pin", "valuation_report", "crb_report"):
        review_and_approve(admin1, admin2, readings[doc_type].id, application_id=app["id"])
    bank = readings["bank_statement"].id
    rows = admin1.get(f"/api/v1/extractions/{bank}/review").get_json()["data"]["transactions"]
    row = next(r for r in rows if r["page_number"] == 2 and r["row_no"] == 4)
    assert admin1.post(f"/api/v1/extractions/{bank}/review/transactions/{row['id']}",
                       {"debit": "7250.50", "balance": "154749.50", "reason": "Misread 7 as 6"}).status_code == 200
    review_and_approve(admin1, admin2, bank, application_id=app["id"])

    # CRB status from the reviewed CRB report, confirmed by a second person.
    crb = admin1.post(f"/api/v1/applications/{app['id']}/crb",
                      {"status": "clear", "status_date": "2026-09-30", "bureau": "SAMPLE CREDIT BUREAU",
                       "extraction_id": readings["crb_report"].id}).get_json()["data"]
    assert admin2.post(f"/api/v1/change-requests/{crb['change_request_id']}/approve").status_code == 200

    # Pre-selection, then the human decision.
    run = staff.post(f"/api/v1/applications/{app['id']}/screen").get_json()["data"]
    assert run["outcome"] == "needs_review" and run["recommendation_only"] is True
    assert CreditDecision.query.count() == 0
    res = admin1.post(f"/api/v1/applications/{app['id']}/decision",
                      {"decision": "more_info", "reason": "Ask for statements covering six months"})
    assert res.status_code == 201

    # The decision log holds the whole trace.
    res = admin1.get(f"/api/v1/applications/{app['id']}/log")
    assert res.status_code == 200, res.get_json()
    log = res.get_json()["data"]
    assert len(log["documents"]) == 5 and len(log["readings"]) == 5
    by_type = {r["extraction"]["declared_type"]: r for r in log["readings"]}
    nid = by_type["national_id"]
    assert nid["extraction"]["model_requested"] == "claude-opus-5-5"
    assert nid["extraction"]["prompt_version"] == "national_id.v1" and nid["extraction"]["schema_version"] == \
        "national_id.v1"
    assert len(nid["extraction"]["document_sha256"]) == 64 and nid["calls"] == 1
    serial = next(v for v in nid["review"]["values"] if v["field"] == "serial_number")
    assert (serial["ai_value"], serial["confirmed_value"], serial["action"]) == ("000000001", "000000002", "correct")
    assert serial["reason"] and nid["review"]["approved_by"] == "admin2@anchorstone.test"
    statement = by_type["bank_statement"]["review"]
    assert statement["rows_corrected"][0]["ai"]["debit"] == "6250.50"
    assert statement["rows_corrected"][0]["confirmed"]["debit"] == "7250.50"
    assert statement["confirmed_metrics"]["metrics"]["avg_monthly_inflow"] == "81666.67"
    assert {c["check"] for c in log["checks"]} == {"name_consistent", "id_number_consistent",
                                                   "cr12_directors_match", "collateral_owner_match"}
    [logged_run] = log["runs"]
    assert logged_run["id"] == run["id"] and logged_run["rule_set_version_no"] == 1
    assert len(logged_run["rules"]) == 9 and all(r["reason"] for r in logged_run["rules"])
    assert {r["rule_id"]: r["result"] for r in logged_run["rules"]}["R3"] == "pass"
    assert log["crb_statuses"][0]["source"] == "crb_report"
    assert [(d["decision"], d["decided_by"]) for d in log["decisions"]] == [("more_info", "admin1@anchorstone.test")]
    actions = [a["action"] for a in log["audit"]]
    for expected in ("CREATE_APPLICATION", "LINK_APPLICATION_DOCUMENT", "ENTER_CRB_STATUS", "SCREEN_APPLICATION",
                     "RECORD_CREDIT_DECISION"):
        assert expected in actions
    assert db.session.get(ScreeningRun, run["id"]).inputs_sha256 == run["inputs_sha256"]
    assert DataAccessLog.query.filter_by(action="view", entity_type="ai_extraction",
                                         user_email="admin1@anchorstone.test").count() >= 5
    assert AuditLog.query.filter_by(action="UPDATE_PARTY_FROM_AI_REVIEW").count() >= 1
    assert staff.get(f"/api/v1/applications/{app['id']}/log").status_code == 403  # no ai.extract.view


def test_ai_12_usage_and_cost_per_month_and_document_type(ai, staff, admin1, admin2):
    p = person(staff)
    app = new_application(staff, p["id"])
    read_into(ai, staff, admin1, app, p["id"], "national_id", "national_id_clean")
    read_into(ai, staff, admin1, app, p["id"], "bank_statement", "bank_statement_page1", "bank_statement_page2",
              "bank_statement_page3")
    res = admin1.get("/api/v1/ai/usage")
    assert res.status_code == 200
    [month] = res.get_json()["data"]["months"]
    assert month["calls"] == 4 and month["readings"] == 2
    assert month["cost_usd"] == "0.213800"  # 0.0314 + 3 × (4,700 × $4/M + 2,100 × $20/M)
    rows = {r["document_type"]: r for r in month["by_type"]}
    assert rows["bank_statement"]["cost_per_reading_usd"] == "0.182400"
    assert rows["national_id"]["model"] == "claude-opus-5-5"
    assert staff.get("/api/v1/ai/usage").status_code == 403


def test_ai_13_accuracy_from_reviews_supports_the_sign_off(ai, staff, admin1, admin2):
    p = person(staff)
    app = new_application(staff, p["id"])
    ex = read_into(ai, staff, admin1, app, p["id"], "national_id", "national_id_clean")
    review_and_approve(admin1, admin2, ex.id, corrections={"full_name": "TESTA SAMPLE MOCKERSON JR"})
    [row] = admin1.get("/api/v1/ai/accuracy").get_json()["data"]
    assert (row["document_type"], row["values"], row["corrected"], row["not_present"]) == ("national_id", 8, 1, 1)
    assert row["accepted"] == 6 and row["accepted_as_read_percent"] == "85.7"
    assert row["confident_but_corrected"] == 1  # full name was read at 0.97 confidence
