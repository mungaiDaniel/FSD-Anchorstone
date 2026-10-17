"""
The one test that calls the real Claude API: the synthetic sample ID card
(tests/fixtures/documents/national_id_clean.png, SAMPLE — NOT A REAL DOCUMENT)
through the whole pipeline. Skipped unless asked for, because it costs money
(about US$0.03) and needs a key:

    ANTHROPIC_LIVE_TEST=1 ANTHROPIC_API_KEY=sk-ant-… venv/Scripts/python -m pytest tests/test_docai_live.py -s

Only the sample is sent. Never point this at a real client's document.
"""
import os

import pytest

from app.database.database import db
from app.DocAI import extractor, service
from app.DocAI.model import ExtractedField, Extraction, ExtractionCall
from test_docai import ai, client_with, run_jobs  # noqa: F401 (ai is a fixture)

pytestmark = pytest.mark.skipif(os.environ.get("ANTHROPIC_LIVE_TEST") != "1" or not os.environ.get("ANTHROPIC_API_KEY"),
                                reason="live API test: set ANTHROPIC_LIVE_TEST=1 and ANTHROPIC_API_KEY")


def test_sample_id_card_through_the_real_api(ai, app, staff, users, monkeypatch):
    monkeypatch.setitem(app.config, "ANTHROPIC_API_KEY", os.environ["ANTHROPIC_API_KEY"])
    extractor.set_client_factory(None)  # the real SDK client
    p, doc = client_with(staff)
    ex = service.request_extraction(p["id"], doc["id"], users["admin1"])
    run_jobs()
    ex = db.session.get(Extraction, ex.id)
    calls = ExtractionCall.query.filter_by(extraction_id=ex.id).all()
    print(f"\nstatus={ex.status} model={[c.model_returned for c in calls]} tokens in/out="
          f"{ex.input_tokens}/{ex.output_tokens} cost=US${ex.cost_usd} reason={ex.status_reason}")
    assert ex.status in ("completed", "needs_review"), ex.status_reason
    assert ex.detected_document_type == "national_id" and ex.readable is True
    got = {f.field_path: f for f in ExtractedField.query.filter_by(extraction_id=ex.id)}
    assert got["id_number"].value == "00000001" and got["id_number"].source_page == 1
    assert "MOCKERSON" in (got["full_name"].value or "")
    assert got["date_of_birth"].value == "1990-01-01"
    assert all(c.request_id and c.raw_ciphertext for c in calls if c.outcome == "ok")
