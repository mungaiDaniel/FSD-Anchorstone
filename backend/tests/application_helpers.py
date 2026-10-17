"""Shared steps for the phase 3b tests: an application, documents read by the (fake) AI,
reviewed by admin1 and approved by admin2."""
from app.database.database import db
from app.DocAI.model import Extraction
from docai_fakes import document, response
from test_docai import consent, make_party, run_jobs, upload

SAMPLE_FILES = {
    "national_id": ("national_id_clean.png", "image/png"), "kra_pin": ("kra_pin_certificate.pdf", "application/pdf"),
    "passport": ("passport_bio_page.pdf", "application/pdf"), "cr12": ("cr12.pdf", "application/pdf"),
    "certificate_of_incorporation": ("certificate_of_incorporation.pdf", "application/pdf"),
    "logbook": ("logbook.pdf", "application/pdf"), "title_deed": ("title_deed.pdf", "application/pdf"),
    "valuation_report": ("valuation_report.pdf", "application/pdf"), "crb_report": ("crb_report.pdf", "application/pdf"),
    "bank_statement": ("bank_statement_3_pages.pdf", "application/pdf"),
    "mpesa_statement": ("mpesa_statement_2_pages.pdf", "application/pdf"),
}


def new_application(api, party_id, **overrides):
    body = {"party_id": party_id, "product_code": "business_loan", "amount_requested": "500000.00",
            "term_months": 12, "indicative_rate_percent": "18"}
    body.update(overrides)
    res = api.post("/api/v1/applications", body)
    assert res.status_code == 201, res.get_json()
    return res.get_json()["data"]


def person(staff, first="Testa Sample", last="Mockerson", id_number="00000001", consented=True):
    p = make_party(staff, first, last, id_number)
    if consented:
        consent(staff, p["id"])
    return p


def organisation(staff, name="Sample Trading Limited", reg_no="PVT-SAMPLE01"):
    res = staff.post("/api/v1/parties", {"party_type": "organisation",
                                         "organisation": {"legal_name": name, "org_type": "sme"},
                                         "identifiers": [{"id_type": "company_reg_no", "value": reg_no}]})
    assert res.status_code == 201, res.get_json()
    org = res.get_json()["data"]
    consent(staff, org["id"])
    return org


def add_director(staff, org_id, person_id):
    res = staff.post(f"/api/v1/parties/{org_id}/relationships",
                     {"relationship": "director", "related_party_id": person_id})
    assert res.status_code == 201, res.get_json()


def read_into(ai, staff, admin1, application, party_id, doc_type, *recorded, answers=None):
    """Upload a sample for the party, add it to the application, and read it with the fake AI."""
    file, content_type = SAMPLE_FILES[doc_type]
    doc = upload(staff, party_id, document(file), doc_type, content_type, file)
    res = admin1.post(f"/api/v1/applications/{application['id']}/documents", {"document_id": doc["id"]})
    assert res.status_code == 201, res.get_json()
    ai.queue(*[response(name, answer=(answers or {}).get(name)) for name in recorded])
    res = admin1.post(f"/api/v1/parties/{party_id}/documents/{doc['id']}/extractions")
    assert res.status_code == 202, res.get_json()
    run_jobs()
    return db.session.get(Extraction, res.get_json()["data"]["id"])


def review_and_approve(maker, checker, ex_id, corrections=None, application_id=None):
    """maker accepts (or applies corrections to) every value and submits; checker approves."""
    corrections = corrections or {}
    body = maker.get(f"/api/v1/extractions/{ex_id}/review").get_json()["data"]
    for f in body["fields"]:
        if f["path"] in corrections:
            payload = {"action": "correct", "value": corrections[f["path"]], "reason": "Checked against the original"}
        elif f["value"] is not None and f["validation"] != "failed":
            payload = {"action": "accept"}
        else:
            payload = {"action": "not_present"}
        res = maker.post(f"/api/v1/extractions/{ex_id}/review/fields/{f['id']}", payload)
        assert res.status_code == 200, (f["path"], res.get_json())
    res = maker.post(f"/api/v1/extractions/{ex_id}/review/submit",
                     {"application_id": application_id} if application_id else None)
    assert res.status_code == 201, res.get_json()
    cr_id = res.get_json()["data"]["change_request_id"]
    res = checker.post(f"/api/v1/change-requests/{cr_id}/approve")
    assert res.status_code == 200, res.get_json()
    db.session.expire_all()
    return cr_id
