"""
AI document extraction (phase 3a).

    POST /api/v1/parties/<id>/documents/<doc_id>/extractions   ask the AI to read a document (queued)
    GET  /api/v1/parties/<id>/extractions                       the client's readings, newest first
    GET  /api/v1/extractions/<id>                               values, pages, transactions, metrics, calls
    POST /api/v1/extractions/<id>/retry                         read the same document again (new record)

Reads are logged in data_access_logs. The raw model output is never returned.
"""
from flask import Blueprint

from app.auth import current_user, requires
from app.DocAI import service
from app.utils.http import ok

docai_v1 = Blueprint("docai_v1", __name__)


@docai_v1.post("/api/v1/parties/<int:party_id>/documents/<uuid:document_id>/extractions")
@requires("ai.extract.run")
def request_extraction(party_id, document_id):
    row = service.request_extraction(party_id, document_id, current_user())
    return ok(row.to_dict(), "Queued: the document will be read shortly.", 202)


@docai_v1.get("/api/v1/parties/<int:party_id>/extractions")
@requires("party.view", "ai.extract.view")
def party_extractions(party_id):
    return ok(service.for_party(party_id, current_user()))


@docai_v1.get("/api/v1/extractions/<int:extraction_id>")
@requires("ai.extract.view")
def extraction_detail(extraction_id):
    return ok(service.detail(extraction_id, current_user()))


@docai_v1.post("/api/v1/extractions/<int:extraction_id>/retry")
@requires("ai.extract.run")
def retry_extraction(extraction_id):
    row = service.retry(extraction_id, current_user())
    return ok(row.to_dict(), "Queued again as a new reading.", 202)
