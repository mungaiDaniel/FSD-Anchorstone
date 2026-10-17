"""Phase 3a: AI document extraction (05-ai-document-pipeline; FSD §15).

No test here calls the real API: the SDK client is replaced by FakeSDK, which
replays recorded responses from tests/fixtures/ai_responses/. The documents sent
are the synthetic samples in tests/fixtures/documents/ (SAMPLE — NOT A REAL
DOCUMENT). The one live call is in test_docai_live.py, skipped unless
ANTHROPIC_LIVE_TEST=1.
"""
import io
import json
import logging
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import text

from app.database.database import db
from app.DocAI import extractor, schema_registry, service, types
from app.DocAI.client import ClaudeClient
from app.DocAI.model import ExtractedField, Extraction, ExtractionCall
from app.Documents import crypto
from app.Documents import service as documents
from app.Documents.model import DataAccessLog
from app.Jobs.model import Job
from app.Jobs.queue import claim, run
from app.Settings import business
from app.Settings.model import SettingVersion
from app.utils.audit_log import AuditLog
from app.utils.dates import utcnow
from app.utils.http import Conflict, Forbidden, ValidationError
from docai_fakes import FakeSDK, api_error, document, recorded, response, timeout

BACKEND = Path(__file__).resolve().parents[1]


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


def consent(api, party_id):
    res = api.post(f"/api/v1/parties/{party_id}/consents", {"purpose": "ai_document_processing", "method": "in_branch"})
    assert res.status_code == 201, res.get_json()
    return res.get_json()["data"]


PDF = b"%PDF-1.4\n" + b"SAMPLE - NOT A REAL DOCUMENT\n" * 20 + b"%%EOF\n"
SAMPLES = {  # declared type → (sample file, content type, recorded response)
    "national_id": ("national_id_clean.png", "image/png", "national_id_clean"),
    "passport": ("passport_bio_page.pdf", "application/pdf", "passport"),
    "kra_pin": ("kra_pin_certificate.pdf", "application/pdf", "kra_pin"),
    "cr12": ("cr12.pdf", "application/pdf", "cr12"),
    "certificate_of_incorporation": ("certificate_of_incorporation.pdf", "application/pdf",
                                     "certificate_of_incorporation"),
    "audited_financial_statements": ("audited_financial_statements.pdf", "application/pdf",
                                     "audited_financial_statements"),
    "title_deed": ("title_deed.pdf", "application/pdf", "title_deed"),
    "logbook": ("logbook.pdf", "application/pdf", "logbook"),
    "valuation_report": ("valuation_report.pdf", "application/pdf", "valuation_report"),
    "crb_report": ("crb_report.pdf", "application/pdf", "crb_report"),
}


@pytest.fixture
def ai(app, monkeypatch, users):
    """AI switched on (a second, approved version of ai.enabled), the SDK faked, pauses recorded."""
    db.session.add(SettingVersion(key="ai.enabled", value=True, effective_from=date(2026, 1, 2), version_no=2,
                                  source="internal_decision", evidence="tests", created_by=users["admin1"].email,
                                  approved_by=users["admin2"].email, approved_at=utcnow()))
    db.session.commit()
    business.clear_cache()
    sdk = FakeSDK()
    sdk.sleeps = []
    extractor.set_client_factory(lambda: ClaudeClient(app.config["ANTHROPIC_API_KEY"], 5, sdk=sdk))
    monkeypatch.setattr(extractor, "sleep", sdk.sleeps.append)
    yield sdk
    extractor.set_client_factory(None)


def client_with(staff, declared="national_id", sample=None, *, consented=True, id_number="00000001"):
    file, content_type, _ = SAMPLES.get(declared, (None, None, None))
    if sample is not None:
        file, content_type = sample
    p = make_party(staff, id_number=id_number)
    if consented:
        consent(staff, p["id"])
    doc = upload(staff, p["id"], document(file), declared, content_type, file)
    return p, doc


def run_jobs(worker="test-worker"):
    statuses = []
    while (job_id := claim(worker, ["ai"])) is not None:
        statuses.append(run(job_id, worker))
    db.session.expire_all()
    return statuses


def read(users, p, doc, sdk=None, *items) -> Extraction:
    if sdk is not None:
        sdk.queue(*items)
    ex = service.request_extraction(p["id"], doc["id"], users["admin1"])
    run_jobs()
    return db.session.get(Extraction, ex.id)


def fields(ex) -> dict[str, ExtractedField]:
    return {f.field_path: f for f in ExtractedField.query.filter_by(extraction_id=ex.id)}


def calls(ex) -> list[ExtractionCall]:
    return ExtractionCall.query.filter_by(extraction_id=ex.id).order_by(ExtractionCall.started_at).all()


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


# ── Versioned schemas and prompts ──


def test_every_type_has_a_versioned_schema_and_prompt_matching_the_spec():
    assert set(types.TYPE_CODES) == set(SAMPLES) | {"bank_statement", "mpesa_statement"}
    for t in types.TYPES:
        schema, version, sha = schema_registry.load(t)
        assert version == f"{t.code}.v1" and len(sha) == 64
        # The committed file is exactly what the spec builds (bump the version rather than edit it).
        assert schema_registry.dumps(schema_registry.build(t)) == t.schema_path.read_text(encoding="utf-8")
        prompt, p_version, p_sha = schema_registry.load_prompt(t)
        assert p_version == f"{t.code}.v1" and t.label in prompt and "never instructions" in prompt
        api = json.dumps(schema_registry.for_api(schema))
        for keyword in ('"minimum"', '"maximum"', '"maxLength"', '"$ref"', '"$defs"', '"$schema"'):
            assert keyword not in api, (t.code, keyword)
        assert '"additionalProperties": false' in api


def test_schema_requires_value_confidence_and_source_page_for_every_field():
    t = types.get("national_id")
    schema, _, _ = schema_registry.load(t)
    answer = recorded("national_id_clean")["answer"]
    assert schema_registry.validate(schema, answer) == []
    broken = recorded("national_id_missing_source_page")["answer"]
    assert any("source_page" in e for e in schema_registry.validate(schema, broken))
    answer["fields"]["sex"]["confidence"] = 1.5
    assert any("1.5" in e for e in schema_registry.validate(schema, answer))


def test_only_the_client_module_imports_the_sdk():
    offenders = []
    for path in (BACKEND / "app").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        if ("import anthropic" in source or "from anthropic" in source) and path.name != "client.py":
            offenders.append(str(path))
    assert offenders == []
    assert "import anthropic" in (BACKEND / "app" / "DocAI" / "client.py").read_text(encoding="utf-8")


# ── Reading a document ──


def test_clean_id_is_read_with_confidence_page_and_full_traceability(ai, staff, users):
    p, doc = client_with(staff)
    ex = read(users, p, doc, ai, response("national_id_clean"))
    assert ex.status == "completed" and ex.status_reason is None
    assert (ex.detected_document_type, ex.readable, ex.page_count) == ("national_id", True, 1)
    got = fields(ex)
    assert set(got) == {f.name for f in types.get("national_id").fields}
    id_number = got["id_number"]
    assert (id_number.value, id_number.confidence, id_number.source_page, id_number.validation) == \
        ("00000001", Decimal("0.980"), 1, "passed")
    assert id_number.source_text == "ID NUMBER 00000001"
    assert got["date_of_birth"].value == "1990-01-01" and got["date_of_birth"].validation == "passed"
    assert got["place_of_birth"].value is None and got["place_of_birth"].validation == "empty"
    assert ex.warnings == ["The card is marked SAMPLE — NOT A REAL DOCUMENT."]

    # Traceability (AI-10): model, prompt and schema versions + hashes, document hash, tokens, cost, raw response.
    t = types.get("national_id")
    assert (ex.model_requested, ex.effort) == ("claude-opus-5-5", "medium")
    assert (ex.prompt_version, ex.prompt_sha256) == schema_registry.load_prompt(t)[1:]
    assert (ex.schema_version, ex.schema_sha256) == schema_registry.load(t)[1:]
    assert ex.document_sha256 == doc["sha256"]
    [call] = calls(ex)
    assert (call.outcome, call.purpose, call.attempt, call.page_number) == ("ok", "extract", 1, None)
    assert (call.model_returned, call.request_id) == ("claude-opus-5-5", "req_sample_national_id_clean")
    assert (call.input_tokens, call.output_tokens) == (2950, 980)
    assert call.cost_usd == Decimal("0.031400")  # 2,950 × $4/M + 980 × $20/M
    assert (ex.input_tokens, ex.output_tokens, ex.cost_usd) == (2950, 980, Decimal("0.031400"))
    assert b"00000001" not in call.raw_ciphertext
    data_key = crypto.unwrap(call.raw_wrapped_key, call.id.bytes, crypto.kek_for(call.raw_key_id))
    raw = json.loads(crypto.open_sealed(call.raw_ciphertext, call.raw_nonce, data_key, call.id.bytes))
    assert raw["model"] == "claude-opus-5-5" and "00000001" in raw["content"][1]["text"]

    # What was sent: the image, the versioned prompt, the schema as structured output, the setting's model.
    [sent] = ai.calls
    assert sent["model"] == "claude-opus-5-5" and sent["system"] == schema_registry.load_prompt(t)[0]
    assert sent["output_config"]["effort"] == "medium"
    assert sent["output_config"]["format"]["schema"] == schema_registry.for_api(schema_registry.load(t)[0])
    block = sent["messages"][0]["content"][0]
    assert block["type"] == "image" and block["source"]["media_type"] == "image/png"
    assert "party" not in json.dumps(sent["messages"][0]["content"][1]).lower()  # no internal ids sent
    assert sent["fallbacks"] == "default" and sent["betas"] == ["server-side-fallback-2026-07-01"]

    process = DataAccessLog.query.filter_by(action="process").one()
    assert (process.user_email, process.entity_id) == ("ai-worker", str(ex.id))
    actions = [a.action for a in AuditLog.query.order_by(AuditLog.id) if "AI_EXTRACTION" in a.action]
    assert actions == ["REQUEST_AI_EXTRACTION", "AI_EXTRACTION_FINISHED"]


@pytest.mark.parametrize("declared", sorted(set(SAMPLES) - {"national_id"}))
def test_each_document_type_is_read_and_every_value_has_confidence_and_page(ai, staff, users, declared):
    p, doc = client_with(staff, declared)
    ex = read(users, p, doc, ai, response(SAMPLES[declared][2]))
    assert ex.status == "completed", ex.status_reason
    got = fields(ex)
    t = types.get(declared)
    assert {f.name for f in t.fields} <= set(got)
    for f in got.values():
        assert f.source_page == 1 and f.confidence is not None and f.validation in ("passed", "empty"), f.field_path
    if declared == "cr12":
        assert got["directors[1].name"].value == "EXEMPLA DUMMY PLACEHOLDER"
        assert got["shareholders[0].number_of_shares"].value == "600"
    assert ai.calls[0]["messages"][0]["content"][0]["type"] == "document"


def test_missing_source_page_gets_exactly_one_repair_call(ai, staff, users):
    p, doc = client_with(staff)
    ex = read(users, p, doc, ai, response("national_id_missing_source_page"), response("national_id_clean"))
    assert ex.status == "completed"
    assert [(c.purpose, c.outcome) for c in calls(ex)] == [("extract", "invalid_output"), ("repair", "ok")]
    assert "source_page" in calls(ex)[0].error
    repair = ai.calls[1]["messages"]
    assert [m["role"] for m in repair] == ["user", "assistant", "user"] and "source_page" in repair[2]["content"]
    assert ex.input_tokens == 2950 * 2 and ex.cost_usd == Decimal("0.031000") + Decimal("0.031400")


def test_a_second_invalid_answer_fails_for_manual_capture(ai, staff, users):
    p, doc = client_with(staff)
    ex = read(users, p, doc, ai, response("national_id_missing_source_page"),
              response("national_id_missing_source_page"))
    assert ex.status == "failed" and "twice" in ex.status_reason and "by hand" in ex.status_reason
    assert len(calls(ex)) == 2 and fields(ex) == {}


def test_wrong_document_type_needs_a_rescan(ai, staff, users):
    p, doc = client_with(staff, sample=("kra_pin_certificate.pdf", "application/pdf"))  # declared national_id
    ex = read(users, p, doc, ai, response("national_id_wrong_type_kra_pin"))
    assert ex.status == "rescan_needed" and ex.detected_document_type == "kra_pin"
    assert "looks like a KRA PIN certificate, not a National ID card" in ex.status_reason
    assert fields(ex) == {}


def test_unreadable_scan_needs_a_rescan_and_nothing_is_guessed(ai, staff, users):
    p, doc = client_with(staff, sample=("national_id_unreadable.png", "image/png"))
    ex = read(users, p, doc, ai, response("national_id_unreadable"))
    assert ex.status == "rescan_needed" and ex.readable is False
    assert "can't be read: The image is heavily blurred" in ex.status_reason and "clearer copy" in ex.status_reason
    assert fields(ex) == {}


def test_values_failing_python_checks_are_kept_and_flagged_for_review(ai, staff, users):
    answer = recorded("national_id_clean")["answer"]
    answer["fields"]["id_number"]["value"] = "1234"
    answer["fields"]["date_of_birth"]["value"] = "2031-01-01"  # after "today" (2026-10-05)
    answer["fields"]["sex"]["source_page"] = 3  # the file has one page
    p, doc = client_with(staff)
    ex = read(users, p, doc, ai, response("national_id_clean", answer=answer))
    got = fields(ex)
    assert ex.status == "needs_review" and "3 value(s) failed checks" in ex.status_reason
    assert (got["id_number"].value, got["id_number"].validation) == ("1234", "failed")
    assert "7 or 8 digits" in got["id_number"].validation_reason
    assert "future" in got["date_of_birth"].validation_reason
    assert "beyond the document's 1 page" in got["sex"].validation_reason


def test_busy_service_is_retried_with_backoff_then_succeeds(ai, staff, users):
    p, doc = client_with(staff)
    ex = read(users, p, doc, ai, api_error(429, retry_after="7"), api_error(529, "Overloaded"),
              response("national_id_clean"))
    assert ex.status == "completed"
    assert [(c.outcome, c.attempt) for c in calls(ex)] == [("retryable_error", 1), ("retryable_error", 2), ("ok", 3)]
    assert calls(ex)[0].request_id == "req_err_429"
    assert len(ai.sleeps) == 2 and ai.sleeps[0] >= 7 and 4 <= ai.sleeps[1] < 5  # retry-after, then 2 s × 2 + jitter


@pytest.mark.parametrize("error", [lambda: api_error(500), lambda: api_error(529), timeout])
def test_after_three_failed_tries_the_document_is_marked_extraction_failed(ai, staff, users, error):
    p, doc = client_with(staff)
    ex = read(users, p, doc, ai, error(), error(), error())
    assert ex.status == "failed" and "didn't respond after 3 tries" in ex.status_reason
    assert "capture the details by hand" in ex.status_reason
    assert [c.outcome for c in calls(ex)] == ["retryable_error"] * 3 and len(ai.sleeps) == 2
    job = db.session.get(Job, ex.job_id)
    assert job.status == "succeeded" and job.attempts == 1  # handled; the queue doesn't call the API again


def test_a_refused_request_is_not_retried(ai, staff, users):
    p, doc = client_with(staff)
    ex = read(users, p, doc, ai, api_error(400, "messages: image too large"))
    assert ex.status == "failed" and "refused the request" in ex.status_reason
    assert [c.outcome for c in calls(ex)] == ["permanent_error"] and ai.sleeps == []


def test_a_model_refusal_fails_for_manual_capture(ai, staff, users):
    p, doc = client_with(staff)
    ex = read(users, p, doc, ai, response("national_id_clean", stop_reason="refusal", text=""))
    assert ex.status == "failed" and "declined" in ex.status_reason
    assert calls(ex)[0].outcome == "refusal" and calls(ex)[0].raw_ciphertext is not None


def test_heic_and_locked_pdfs_need_a_rescan_without_calling_the_api(ai, staff, users):
    from pypdf import PdfReader, PdfWriter

    heic = b"\x00\x00\x00\x18ftypheic" + b"\x00" * 64
    p, doc = client_with(staff, sample=("national_id_clean.png", "image/png"))
    other = upload(staff, p["id"], heic, "passport", "image/heic", "photo.heic")
    ex = service.request_extraction(p["id"], other["id"], users["admin1"])
    run_jobs()
    ex = db.session.get(Extraction, ex.id)
    assert ex.status == "rescan_needed" and "HEIC" in ex.status_reason

    writer = PdfWriter()
    writer.append(PdfReader(io.BytesIO(document("kra_pin_certificate.pdf"))))
    writer.encrypt("client-password")
    buf = io.BytesIO()
    writer.write(buf)
    locked = upload(staff, p["id"], buf.getvalue(), "kra_pin", "application/pdf", "locked.pdf")
    ex = service.request_extraction(p["id"], locked["id"], users["admin1"])
    run_jobs()
    ex = db.session.get(Extraction, ex.id)
    assert ex.status == "rescan_needed" and "password-protected" in ex.status_reason
    assert ai.calls == []


# ── Gates ──


def test_no_consent_means_no_ai_and_a_clear_message(ai, staff, users):
    p, doc = client_with(staff, consented=False)
    with pytest.raises(Forbidden, match="hasn't consented to automatic document reading.*by hand"):
        service.request_extraction(p["id"], doc["id"], users["admin1"])
    assert Extraction.query.count() == 0 and Job.query.filter_by(name="ai.extract_document").count() == 0


def test_consent_withdrawn_after_queueing_stops_the_job(ai, staff, users):
    p, doc = client_with(staff)
    ex = service.request_extraction(p["id"], doc["id"], users["admin1"])
    c = staff.get(f"/api/v1/parties/{p['id']}/consents").get_json()["data"][0]
    assert staff.post(f"/api/v1/parties/{p['id']}/consents/{c['id']}/withdraw").status_code == 200
    assert run_jobs() == ["failed"]
    ex = db.session.get(Extraction, ex.id)
    assert ex.status == "failed" and "hasn't consented" in ex.status_reason
    job = db.session.get(Job, ex.job_id)
    assert job.attempts == 1 and ai.calls == []  # not retried, nothing sent


def test_ai_switched_off_refuses_and_leaves_manual_capture(staff, users):
    p, doc = client_with(staff)
    assert business.get("ai.enabled") is False  # the seeded default
    with pytest.raises(Conflict, match="switched off.*by hand"):
        service.request_extraction(p["id"], doc["id"], users["admin1"])


def test_only_readable_types_of_this_clients_documents(ai, staff, users):
    p, doc = client_with(staff)
    photo = upload(staff, p["id"], document("national_id_clean.png"), "photo", "image/png", "photo.png")
    with pytest.raises(ValidationError, match="can't be read automatically"):
        service.request_extraction(p["id"], photo["id"], users["admin1"])
    other = make_party(staff, "Exempla", "Dummy", "00000002")
    with pytest.raises(Exception, match="not found"):
        service.request_extraction(other["id"], doc["id"], users["admin1"])


def test_one_reading_at_a_time_and_a_retry_is_a_new_record(ai, staff, users):
    p, doc = client_with(staff)
    first = service.request_extraction(p["id"], doc["id"], users["admin1"])
    with pytest.raises(Conflict, match="already being read"):
        service.request_extraction(p["id"], doc["id"], users["admin1"])
    with pytest.raises(Conflict, match="still being read"):
        service.retry(first.id, users["admin1"])
    ai.queue(api_error(400))
    run_jobs()
    failed = db.session.get(Extraction, first.id)
    before = failed.to_dict()
    ai.queue(response("national_id_clean"))
    second = service.retry(failed.id, users["admin1"])
    run_jobs()
    second = db.session.get(Extraction, second.id)
    assert second.status == "completed" and second.supersedes_id == first.id
    assert db.session.get(Extraction, first.id).to_dict() == before  # the failed reading is kept as it was
    assert AuditLog.query.filter_by(action="RETRY_AI_EXTRACTION").count() == 1


def test_a_rerun_job_skips_a_finished_extraction_and_rereads_one_left_running(ai, staff, users):
    p, doc = client_with(staff)
    ex = read(users, p, doc, ai, response("national_id_clean"))
    assert extractor.run_extraction(ex.id) == {"skipped": "completed"}
    p2, doc2 = client_with(staff, id_number="00000002")
    ex2 = service.request_extraction(p2["id"], doc2["id"], users["admin1"])
    db.session.execute(text("UPDATE ai_extractions SET status = 'running', started_at = now() WHERE id = :i"),
                       {"i": ex2.id})
    db.session.commit()
    ai.queue(response("national_id_clean"))
    assert extractor.run_extraction(ex2.id)["status"] == "completed"


# ── The API key stays secret ──


def test_the_api_key_never_appears_in_errors_records_or_logs(ai, app, staff, users, caplog):
    key = app.config["ANTHROPIC_API_KEY"]
    p, doc = client_with(staff)
    caplog.set_level(logging.DEBUG)
    ex = read(users, p, doc, ai, api_error(401, f"invalid x-api-key {key}"))
    assert ex.status == "failed"
    assert key not in ex.status_reason and "[redacted]" in calls(ex)[0].error
    dumped = json.dumps([ex.to_dict()] + [c.to_dict() for c in calls(ex)])
    assert key not in dumped and key not in caplog.text
    rows = db.session.execute(text("SELECT description, new_value::text FROM audit_logs")).all()
    assert all(key not in (r[0] or "") + (r[1] or "") for r in rows)
