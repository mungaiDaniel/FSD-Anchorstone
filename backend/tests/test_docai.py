"""Phase 3a: AI document extraction (05-ai-document-pipeline; FSD §15).

No test here calls the real API: the SDK client is replaced by FakeSDK, which
replays recorded responses from tests/fixtures/ai_responses/. The documents sent
are the synthetic samples in tests/fixtures/documents/ (SAMPLE — NOT A REAL
DOCUMENT). The one live call is in test_docai_live.py, skipped unless
ANTHROPIC_LIVE_TEST=1.
"""
import io
import uuid

import pytest
from sqlalchemy import text

from app.database.database import db
from app.DocAI.model import Extraction
from app.Documents import service as documents
from app.Documents.model import DataAccessLog
from app.utils.dates import utcnow


def make_party(api, first="Testa", last="Mockerson", id_number="00000001"):
    res = api.post("/api/v1/parties", {"party_type": "person", "person": {"first_name": first, "last_name": last},
                                       "identifiers": [{"id_type": "national_id", "value": id_number}]})
    assert res.status_code == 201, res.get_json()
    return res.get_json()["data"]


def upload(api, party_id, data, document_type="national_id", content_type="application/pdf", name="sample.pdf"):
    res = api.client.post(f"/api/v1/parties/{party_id}/documents", headers=api.headers,
                          content_type="multipart/form-data",
                          data={"document_type": document_type, "file": (io.BytesIO(data), name, content_type)})
    assert res.status_code == 201, res.get_json()
    return res.get_json()["data"]


PDF = b"%PDF-1.4\n" + b"SAMPLE - NOT A REAL DOCUMENT\n" * 20 + b"%%EOF\n"


def _raw_extraction(party_id, document_id, status="queued"):
    row = Extraction(party_id=party_id, document_id=uuid.UUID(document_id), declared_type="national_id",
                     status=status, model_requested="claude-opus-5-5", effort="medium", prompt_version="national_id.v1",
                     prompt_sha256="a" * 64, schema_version="national_id.v1", schema_sha256="b" * 64,
                     document_sha256="c" * 64, requested_by="staff@anchorstone.test", requested_at=utcnow(),
                     finished_at=None if status in ("queued", "running") else utcnow(),
                     status_reason=None if status in ("queued", "running", "completed") else "test")
    db.session.add(row)
    db.session.commit()
    return row


# ── Records: the database keeps them as they were written ──


def test_a_worker_reads_a_document_with_a_logged_process_action(staff):
    p = make_party(staff)
    doc = upload(staff, p["id"], PDF)
    got, data = documents.read_for_processing(uuid.UUID(doc["id"]), "ai-worker", ("ai_extraction", "1"))
    assert data == PDF and got.sha256 == doc["sha256"]
    log = DataAccessLog.query.filter_by(action="process").one()
    assert (log.user_email, log.user_id, log.entity_type, log.entity_id) == ("ai-worker", None, "ai_extraction", "1")


def test_a_finished_extraction_is_frozen_and_never_deleted(staff):
    p = make_party(staff)
    doc = upload(staff, p["id"], PDF)
    running = _raw_extraction(p["id"], doc["id"], "running")
    # While it runs, status and results may change; what was sent and how may not.
    db.session.execute(text("UPDATE ai_extractions SET page_count = 1 WHERE id = :i"), {"i": running.id})
    with pytest.raises(Exception, match="can't be changed"):
        db.session.execute(text("UPDATE ai_extractions SET model_requested = 'other' WHERE id = :i"),
                           {"i": running.id})
    db.session.rollback()
    done = _raw_extraction(p["id"], doc["id"], "completed")
    for sql in ("UPDATE ai_extractions SET status_reason = 'x' WHERE id = :i",
                "DELETE FROM ai_extractions WHERE id = :i"):
        with pytest.raises(Exception, match="request a new extraction|never deleted"):
            db.session.execute(text(sql), {"i": done.id})
        db.session.rollback()


def test_extraction_detail_tables_are_insert_only(staff):
    p = make_party(staff)
    doc = upload(staff, p["id"], PDF)
    ex = _raw_extraction(p["id"], doc["id"], "running")
    db.session.execute(text("INSERT INTO ai_extracted_fields (extraction_id, field_path, value, validation, "
                            "date_created, date_updated) VALUES (:i, 'id_number', '00000001', 'passed', now(), now())"),
                       {"i": ex.id})
    db.session.commit()
    for sql in ("UPDATE ai_extracted_fields SET value = '1'", "DELETE FROM ai_extracted_fields"):
        with pytest.raises(Exception, match="insert-only"):
            db.session.execute(text(sql))
        db.session.rollback()
