"""Phase 3b: pre-screen applications, the instalment ESTIMATE and the CRB status.

Tests are named after the AI requirement they cover (mapping in 05-ai-document-pipeline.md):
AI-07 staff confirmation, AI-08 pre-screening rules (the estimate feeds the inflow rule),
AI-09 people decide.
"""
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.Applications.estimate import estimate
from app.Applications.model import ApplicationCrbStatus, LoanApplication
from app.database.database import db
from app.utils.audit_log import AuditLog
from test_docai import make_party, upload
from docai_fakes import document


def new_application(api, party_id, **overrides):
    body = {"party_id": party_id, "product_code": "business_loan", "amount_requested": "500,000.00",
            "term_months": 12, "indicative_rate_percent": "18"}
    body.update(overrides)
    res = api.post("/api/v1/applications", body)
    assert res.status_code == 201, res.get_json()
    return res.get_json()["data"]


# ── The estimate (temporary; phase 5 replaces it) ──


@pytest.mark.parametrize("product, amount, term, rate, instalment, final", [
    ("business_loan", "500000", 12, "18", "45840.00", "45840.00"),        # 500,000 × 0.015 ÷ (1 − 1.015^−12)
    ("asset_finance", "1200000", 36, "21.5", "45518.73", "45518.73"),
    ("business_loan", "100000", 4, "0", "25000.00", "25000.00"),           # no interest: principal ÷ months
    ("bridge_loan", "300000", 3, "24", "6000.00", "306000.00"),            # 2% a month, principal at maturity
])
def test_ai_08_estimated_instalment_matches_hand_calculation(product, amount, term, rate, instalment, final):
    got = estimate(product, Decimal(amount), term, Decimal(rate))
    assert got == (Decimal(instalment), Decimal(final))


def test_ai_08_estimate_is_labelled_and_stored_on_the_application(staff):
    p = make_party(staff)
    a = new_application(staff, p["id"])
    assert (a["application_no"], a["estimated_instalment"], a["repayment"]) == ("AP-0000001", "45840.00",
                                                                                "amortising")
    assert "Estimate only" in a["estimate_note"]
    res = staff.get("/api/v1/applications/estimate?product_code=bridge_loan&amount_requested=300000"
                    "&term_months=2&indicative_rate_percent=24")
    body = res.get_json()["data"]
    assert (body["estimated_instalment"], body["estimated_final_payment"]) == ("6000.00", "306000.00")
    assert "Estimate only" in body["estimate_note"]
    assert AuditLog.query.filter_by(action="CREATE_APPLICATION").count() == 1


@pytest.mark.parametrize("override, message", [
    ({"product_code": "car_loan"}, "product_code must be one of"),
    ({"term_months": 30}, "runs 3 to 24 months"),
    ({"product_code": "bridge_loan", "term_months": 6}, "runs 1 to 3 months"),
    ({"amount_requested": "0"}, "greater than zero"),
    ({"amount_requested": "10.005"}, "more than 2 decimal places"),
    ({"indicative_rate_percent": "101"}, "between 0 and 100"),
    ({"business_start_date": "2030-01-01"}, "future"),
])
def test_ai_08_invalid_applications_are_refused(staff, override, message):
    p = make_party(staff)
    body = {"party_id": p["id"], "product_code": "business_loan", "amount_requested": "500000", "term_months": 12,
            "indicative_rate_percent": "18", **override}
    res = staff.post("/api/v1/applications", body)
    assert res.status_code == 400 and message in res.get_json()["message"]
    assert LoanApplication.query.count() == 0


# ── Guarantors and documents ──


def test_ai_09_documents_and_guarantors_belong_to_the_application(staff):
    p = make_party(staff)
    g = make_party(staff, "Exempla", "Dummy", "00000002")
    stranger = make_party(staff, "Other", "Person", "00000003")
    a = new_application(staff, p["id"])
    assert staff.post(f"/api/v1/applications/{a['id']}/guarantors", {"party_id": g["id"]}).status_code == 201
    assert staff.post(f"/api/v1/applications/{a['id']}/guarantors", {"party_id": g["id"]}).status_code == 409
    assert staff.post(f"/api/v1/applications/{a['id']}/guarantors", {"party_id": p["id"]}).status_code == 400

    own = upload(staff, p["id"], document("national_id_clean.png"), "national_id", "image/png", "id.png")
    logbook = upload(staff, g["id"], document("logbook.pdf"), "logbook", "application/pdf", "logbook.pdf")
    foreign = upload(staff, stranger["id"], document("kra_pin_certificate.pdf"), "kra_pin", "application/pdf",
                     "kra.pdf")
    for doc in (own, logbook):
        assert staff.post(f"/api/v1/applications/{a['id']}/documents", {"document_id": doc["id"]}).status_code == 201
    assert staff.post(f"/api/v1/applications/{a['id']}/documents", {"document_id": own["id"]}).status_code == 409
    assert staff.post(f"/api/v1/applications/{a['id']}/documents", {"document_id": foreign["id"]}).status_code == 404
    detail = staff.get(f"/api/v1/applications/{a['id']}").get_json()["data"]
    assert [d["document_type"] for d in detail["documents"]] == ["national_id", "logbook"]
    assert [x["party_no"] for x in detail["guarantors"]] == [g["party_no"]]


# ── CRB status: entered by staff, confirmed by a second person (AI-07) ──


def test_ai_07_crb_status_needs_a_second_person(staff, admin1, admin2):
    p = make_party(staff)
    a = new_application(staff, p["id"])
    res = admin1.post(f"/api/v1/applications/{a['id']}/crb",
                      {"status": "previously_listed_cleared", "status_date": "2026-09-30", "bureau": "Sample Bureau"})
    assert res.status_code == 201, res.get_json()
    crb = res.get_json()["data"]
    assert crb["confirmed_at"] is None and crb["change_request_id"]
    assert staff.get(f"/api/v1/applications/{a['id']}").get_json()["data"]["crb"] is None  # not used until confirmed
    # A second entry can't be queued while one waits.
    assert admin1.post(f"/api/v1/applications/{a['id']}/crb", {"status": "clear", "status_date": "2026-09-30",
                                                                 "bureau": "X"}).status_code == 409
    # The maker can't confirm; staff can't either (no application.crb.confirm).
    assert admin1.post(f"/api/v1/change-requests/{crb['change_request_id']}/approve").status_code == 403
    assert staff.post(f"/api/v1/change-requests/{crb['change_request_id']}/approve").status_code == 403
    assert admin2.post(f"/api/v1/change-requests/{crb['change_request_id']}/approve").status_code == 200
    confirmed = staff.get(f"/api/v1/applications/{a['id']}").get_json()["data"]["crb"]
    assert (confirmed["status"], confirmed["confirmed_by"]) == ("previously_listed_cleared", "admin2@anchorstone.test")
    # The database refuses maker = checker and any change once confirmed.
    row = db.session.get(ApplicationCrbStatus, crb["id"])
    with pytest.raises(Exception, match="can't be changed"):
        db.session.execute(text("UPDATE application_crb_statuses SET status = 'clear' WHERE id = :i"), {"i": row.id})
    db.session.rollback()
    other = ApplicationCrbStatus(application_id=a["id"], status="clear", status_date=row.status_date, bureau="X",
                                 entered_by="admin1@anchorstone.test", entered_at=row.entered_at)
    db.session.add(other)
    db.session.commit()
    with pytest.raises(Exception, match="ck_application_crb_statuses_maker_checker"):
        db.session.execute(text("UPDATE application_crb_statuses SET confirmed_by = 'ADMIN1@anchorstone.test', "
                                "confirmed_at = now() WHERE id = :i"), {"i": other.id})
    db.session.rollback()


@pytest.mark.parametrize("body, message", [
    ({"status": "blacklisted", "status_date": "2026-09-30", "bureau": "X"}, "status must be one of"),
    ({"status": "clear", "status_date": "2027-01-01", "bureau": "X"}, "future"),
    ({"status": "clear", "status_date": "2026-09-30", "bureau": " "}, "bureau is required"),
    ({"status": "clear", "status_date": "2026-09-30", "bureau": "X", "extraction_id": 99}, "CRB report reading"),
])
def test_ai_07_invalid_crb_entries_are_refused(staff, body, message):
    p = make_party(staff)
    a = new_application(staff, p["id"])
    res = staff.post(f"/api/v1/applications/{a['id']}/crb", body)
    assert res.status_code == 400 and message in res.get_json()["message"]
