"""Phase 2b item 5: client documents through the encrypted store, and consent capture."""
import io
import uuid

import pytest
from sqlalchemy import text

from app.database.database import db
from app.Documents.model import DataAccessLog, Document
from app.Documents.store import get_store
from app.Jobs.model import Job
from app.Jobs.queue import claim, enqueue, run
from app.Jobs.registry import TASKS, TaskDef
from app.Parties.documents import PARTY_DOCUMENT_TYPES
from app.utils.http import Forbidden

PDF = b"%PDF-1.4\n" + b"Jane Doe, ID 12345678\n" * 100 + b"%%EOF\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def party(api):
    res = api.post("/api/v1/parties", {"party_type": "person", "person": {"first_name": "Jane", "last_name": "Doe"},
                                       "identifiers": [{"id_type": "national_id", "value": "12345678"}]})
    assert res.status_code == 201
    return res.get_json()["data"]


def upload(api, party_id, document_type="national_id", data=PDF, content_type="application/pdf", expect=201):
    res = api.client.post(f"/api/v1/parties/{party_id}/documents", headers=api.headers, content_type="multipart/form-data",
                          data={"document_type": document_type, "file": (io.BytesIO(data), "scan.pdf", content_type)})
    assert res.status_code == expect, res.get_json()
    return res.get_json()


def test_document_types_match_fsd_section_5_1():
    fsd_5_1 = {"national_id", "passport", "kra_pin", "cr12", "certificate_of_incorporation", "bank_statement",
               "mpesa_statement", "audited_financial_statements", "title_deed", "logbook", "valuation_report"}
    # crb_report: added by the phase 3a brief (the AI reads it too).
    assert set(PARTY_DOCUMENT_TYPES) == fsd_5_1 | {"crb_report", "photo", "signature", "consent_form", "other"}


def test_upload_is_linked_to_the_client_and_encrypted(staff, admin1):
    p = party(staff)
    doc = upload(staff, p["id"])["data"]
    assert doc["links"] == [{"entity_type": "party", "entity_id": str(p["id"]), "purpose": "national_id"}]
    assert doc["sensitive"] is True and doc["uploaded_by"] == "staff@anchorstone.test"
    blob = get_store().get(db.session.get(Document, uuid.UUID(doc["id"])).storage_key)
    assert b"Jane Doe" not in blob and b"%PDF" not in blob
    # Read through the store only; every read is logged; staff can't open sensitive files.
    assert staff.get(f"/api/v1/documents/{doc['id']}/content").status_code == 403
    res = admin1.get(f"/api/v1/documents/{doc['id']}/content")
    assert res.status_code == 200 and res.data == PDF
    actions = [l.action for l in DataAccessLog.query.filter_by(document_id=uuid.UUID(doc["id"])).order_by(DataAccessLog.id)]
    assert actions == ["upload", "download"]


def test_replaced_documents_are_kept_as_earlier_versions(staff):
    p = party(staff)
    first = upload(staff, p["id"], "photo", PNG, "image/png")["data"]
    second = upload(staff, p["id"], "photo", PNG + b"\x01", "image/png")["data"]
    upload(staff, p["id"], "other")
    upload(staff, p["id"], "other")
    docs = staff.get(f"/api/v1/parties/{p['id']}/documents").get_json()["data"]
    by_id = {d["id"]: d for d in docs}
    assert by_id[second["id"]]["current"] is True and by_id[first["id"]]["current"] is False
    assert by_id[first["id"]]["label"] == "Photo"
    assert sum(d["current"] for d in docs if d["document_type"] == "other") == 2


def test_wrong_document_type_and_permissions_refused(client, staff):
    p = party(staff)
    assert "document_type must be one of" in upload(staff, p["id"], "payslip", expect=400)["message"]
    assert upload(staff, p["id"], "national_id", b"not a pdf", expect=400)
    assert upload(staff, 999, expect=404)
    res = client.post(f"/api/v1/parties/{p['id']}/documents", data={})
    assert res.status_code == 401
    db.session.execute(text("DELETE FROM role_permissions WHERE permission_code = 'document.upload' "
                            "AND role_id = (SELECT id FROM roles WHERE legacy_role = 'user')"))
    db.session.commit()
    assert upload(staff, p["id"], expect=403)


# ── Consent ──


def test_consent_recorded_with_date_method_and_who_captured_it(staff):
    p = party(staff)
    res = staff.post(f"/api/v1/parties/{p['id']}/consents",
                     {"purpose": "ai_document_processing", "method": "in_branch", "granted_on": "2026-10-01"})
    assert res.status_code == 201, res.get_json()
    c = res.get_json()["data"]
    assert (c["granted_on"], c["method"], c["captured_by"], c["notice_version"], c["status"]) == \
        ("2026-10-01", "in_branch", "staff@anchorstone.test", "v1", "active")
    assert staff.post(f"/api/v1/parties/{p['id']}/consents",
                      {"purpose": "ai_document_processing", "method": "email"}).status_code == 409
    row = db.session.execute(text("SELECT action, user_email FROM audit_logs WHERE action = 'RECORD_CONSENT'")).one()
    assert row.user_email == "staff@anchorstone.test"


def test_signed_form_needs_the_uploaded_form(staff):
    p = party(staff)
    res = staff.post(f"/api/v1/parties/{p['id']}/consents", {"purpose": "marketing", "method": "signed_form"})
    assert res.status_code == 400 and "Upload the signed consent form" in res.get_json()["message"]
    other = staff.post("/api/v1/parties", {"party_type": "person", "person": {"first_name": "O", "last_name": "P"}}).get_json()["data"]
    foreign = upload(staff, other["id"], "consent_form")["data"]
    res = staff.post(f"/api/v1/parties/{p['id']}/consents",
                     {"purpose": "marketing", "method": "signed_form", "evidence_document_id": foreign["id"]})
    assert res.status_code == 400 and "uploaded to this client" in res.get_json()["message"]
    form = upload(staff, p["id"], "consent_form")["data"]
    res = staff.post(f"/api/v1/parties/{p['id']}/consents",
                     {"purpose": "marketing", "method": "signed_form", "evidence_document_id": form["id"]})
    assert res.status_code == 201 and res.get_json()["data"]["evidence_document_id"] == form["id"]


def test_consent_invalid_input_refused(staff):
    p = party(staff)
    for body in ({"purpose": "everything", "method": "in_branch"}, {"purpose": "marketing", "method": "phone"},
                 {"purpose": "marketing", "method": "in_branch", "granted_on": "2030-01-01"}):
        assert staff.post(f"/api/v1/parties/{p['id']}/consents", body).status_code == 400


def test_consent_withdrawn_never_deleted(staff):
    p = party(staff)
    c = staff.post(f"/api/v1/parties/{p['id']}/consents", {"purpose": "marketing", "method": "email"}).get_json()["data"]
    res = staff.post(f"/api/v1/parties/{p['id']}/consents/{c['id']}/withdraw", {"note": "Asked by phone"})
    assert res.status_code == 200 and res.get_json()["data"]["status"] == "withdrawn"
    assert staff.post(f"/api/v1/parties/{p['id']}/consents/{c['id']}/withdraw").status_code == 409
    # Consent can be given again; both rows stay.
    assert staff.post(f"/api/v1/parties/{p['id']}/consents", {"purpose": "marketing", "method": "email"}).status_code == 201
    assert len(staff.get(f"/api/v1/parties/{p['id']}/consents").get_json()["data"]) == 2
    with pytest.raises(Exception, match="never deleted"):
        db.session.execute(text("DELETE FROM party_consents"))
        db.session.flush()
    db.session.rollback()


@pytest.fixture
def ai_task():
    """A stand-in for the phase 3 extraction job, declared like it will be."""
    TASKS["test.ai_extract"] = TaskDef("test.ai_extract", lambda args: {"read": args["party_id"]}, "default", 1, 60,
                                       consent_purpose="ai_document_processing")
    yield "test.ai_extract"
    TASKS.pop("test.ai_extract", None)


def test_ai_job_refused_without_consent(staff, ai_task):
    p = party(staff)
    with pytest.raises(Forbidden, match="consented to automatic document reading"):
        enqueue(ai_task, {"party_id": p["id"]})
    with pytest.raises(Exception, match="needs the client"):
        enqueue(ai_task, {})
    db.session.rollback()

    c = staff.post(f"/api/v1/parties/{p['id']}/consents",
                   {"purpose": "ai_document_processing", "method": "in_branch"}).get_json()["data"]
    job_id = enqueue(ai_task, {"party_id": p["id"]})
    db.session.commit()
    assert job_id is not None

    # Withdrawn before the worker gets to it: the job itself refuses to run.
    staff.post(f"/api/v1/parties/{p['id']}/consents/{c['id']}/withdraw")
    assert claim("test-worker") == job_id
    run(job_id, "test-worker")
    job = db.session.get(Job, job_id)
    db.session.refresh(job)
    assert job.status == "failed" and "consented" in job.last_error


def test_ai_job_runs_with_consent(staff, ai_task):
    p = party(staff)
    staff.post(f"/api/v1/parties/{p['id']}/consents", {"purpose": "ai_document_processing", "method": "in_branch"})
    job_id = enqueue(ai_task, {"party_id": p["id"]})
    db.session.commit()
    assert claim("test-worker") == job_id
    run(job_id, "test-worker")
    job = db.session.get(Job, job_id)
    db.session.refresh(job)
    assert job.status == "succeeded" and job.result == {"read": p["id"]}
