"""
Requesting and reading AI document extractions (phase 3a).

    request_extraction(party_id, document_id, actor)   checks, then queues job ai.extract_document
    retry(extraction_id, actor)                         a new extraction of the same document
    for_party(party_id, actor) / detail(id, actor)      what was read; every read is logged

Gates, in order (each refusal leaves the manual capture path open):
    ai.enabled is on (two approvers)                    else 409
    the document belongs to the client, is active and
    of a type the AI reads                              else 404 / 409 / 400
    the client has consented to automatic document
    reading (party_consents, 05 §9.1)                   else 403, checked again when the job runs
    no reading of the same document is in progress      else 409

The model, effort, prompt and schema versions and the document's SHA-256 are copied
onto the extraction now, so what runs is what was requested.
"""
import uuid

from flask import current_app

from app.Admin.model import User
from app.database.database import db
from app.DocAI import schema_registry, types
from app.DocAI.model import (
    EXTRACTION_FAILED,
    EXTRACTION_FINISHED,
    EXTRACTION_QUEUED,
    EXTRACTION_RUNNING,
    ExtractedField,
    Extraction,
    ExtractionCall,
    StatementMetric,
    StatementMetricInput,
    StatementPage,
    StatementTransaction,
)
from app.Documents.model import DataAccessLog, Document, DocumentLink
from app.Jobs.queue import assert_consent, enqueue
from app.Jobs.registry import TASKS
from app.Parties import service as parties
from app.Settings import business
from app.utils.audit_log import create_audit_log, get_client_ip
from app.utils.dates import utcnow
from app.utils.http import Conflict, NotFound, ValidationError

TASK = "ai.extract_document"


def _document_for(party_id: int, document_id) -> Document:
    try:
        doc_id = uuid.UUID(str(document_id))
    except ValueError:
        raise NotFound("Document not found.")
    linked = DocumentLink.query.filter_by(document_id=doc_id, entity_type="party", entity_id=str(party_id)).first()
    doc = db.session.get(Document, doc_id) if linked else None
    if doc is None:
        raise NotFound("Document not found for this client.")
    return doc


def request_extraction(party_id: int, document_id, actor: User, supersedes: Extraction | None = None) -> Extraction:
    if not business.get("ai.enabled"):
        raise Conflict("Automatic document reading is switched off (setting ai.enabled). Capture the details by hand.")
    party = parties.get_party(party_id)
    if party.status == "merged":
        raise Conflict("This client was merged into another record.")
    doc = _document_for(party.id, document_id)
    if doc.status != "active":
        raise Conflict("This document was destroyed and can't be read.")
    t = types.get(doc.document_type)
    if t is None:
        readable = ", ".join(types.label(c) for c in types.TYPE_CODES)
        raise ValidationError(f"Documents of this type can't be read automatically. The AI reads: {readable}.")
    if not current_app.config.get("ANTHROPIC_API_KEY"):
        raise Conflict("The AI service isn't configured on the server. Capture the details by hand.")
    assert_consent(TASKS[TASK], {"party_id": party.id})
    busy = (Extraction.query.filter(Extraction.document_id == doc.id,
                                    Extraction.status.in_((EXTRACTION_QUEUED, EXTRACTION_RUNNING))).first())
    if busy is not None:
        raise Conflict(f"This document is already being read (extraction {busy.id}).")

    _, schema_version, schema_sha = schema_registry.load(t)
    _, prompt_version, prompt_sha = schema_registry.load_prompt(t)
    row = Extraction(party_id=party.id, document_id=doc.id, declared_type=t.code, status=EXTRACTION_QUEUED,
                     model_requested=str(business.get("ai.model_extract")), effort=str(business.get("ai.effort")),
                     prompt_version=prompt_version, prompt_sha256=prompt_sha, schema_version=schema_version,
                     schema_sha256=schema_sha, document_sha256=doc.sha256, requested_by=actor.email,
                     requested_at=utcnow(), supersedes_id=supersedes.id if supersedes else None)
    db.session.add(row)
    db.session.flush()
    row.job_id = enqueue(TASK, {"party_id": party.id, "extraction_id": row.id}, enqueued_by=actor.email)
    create_audit_log("RETRY_AI_EXTRACTION" if supersedes else "REQUEST_AI_EXTRACTION", target_type="ai_extraction",
                     target_id=row.id, target_name=party.party_no,
                     description=f"{t.label} ({doc.id}) with {row.model_requested}"
                                 + (f", replacing extraction {supersedes.id}" if supersedes else ""),
                     new_value={"document_id": str(doc.id), "declared_type": t.code, "model": row.model_requested,
                                "prompt_version": prompt_version, "schema_version": schema_version})
    db.session.commit()
    return row


def get_extraction(extraction_id: int) -> Extraction:
    row = db.session.get(Extraction, extraction_id)
    if row is None:
        raise NotFound("Extraction not found.")
    return row


def retry(extraction_id: int, actor: User) -> Extraction:
    old = get_extraction(extraction_id)
    if old.status not in EXTRACTION_FINISHED:
        raise Conflict("This document is still being read.")
    return request_extraction(old.party_id, old.document_id, actor, supersedes=old)


def refuse_for_withdrawn_consent(args: dict, message: str) -> None:
    """The job is refused at run time (consent withdrawn after it was queued): close the extraction."""
    from app.DocAI.extractor import finish

    row = db.session.query(Extraction).filter_by(id=args.get("extraction_id")).with_for_update().one_or_none()
    if row is not None and row.status not in EXTRACTION_FINISHED:
        finish(row, EXTRACTION_FAILED, message)


def _log_view(row: Extraction, actor: User) -> None:
    """Extracted values are the client's personal data: every view is logged like a document view."""
    from flask import has_request_context, request

    db.session.add(DataAccessLog(
        user_id=actor.id, user_email=actor.email, document_id=row.document_id, entity_type="ai_extraction",
        entity_id=str(row.id), action="view", ip_address=get_client_ip() if has_request_context() else None,
        user_agent=(request.headers.get("User-Agent") or "")[:255] if has_request_context() else None,
        at=utcnow()))


def for_party(party_id: int, actor: User) -> list[dict]:
    parties.get_party(party_id)
    rows = Extraction.query.filter_by(party_id=party_id).order_by(Extraction.requested_at.desc(),
                                                                  Extraction.id.desc()).all()
    for row in rows:
        _log_view(row, actor)
    db.session.commit()
    return [{**r.to_dict(), "label": types.label(r.declared_type)} for r in rows]


def detail(extraction_id: int, actor: User) -> dict:
    row = get_extraction(extraction_id)
    fields = ExtractedField.query.filter_by(extraction_id=row.id).order_by(ExtractedField.id).all()
    pages = StatementPage.query.filter_by(extraction_id=row.id).order_by(StatementPage.page_number).all()
    txns = (StatementTransaction.query.filter_by(extraction_id=row.id)
            .order_by(StatementTransaction.page_number, StatementTransaction.row_no).all())
    metrics = StatementMetric.query.filter_by(extraction_id=row.id).order_by(StatementMetric.id).all()
    inputs: dict[int, list[int]] = {}
    keywords: dict[int, dict[str, str]] = {}
    if metrics:
        for link in StatementMetricInput.query.filter(StatementMetricInput.metric_id.in_([m.id for m in metrics])):
            inputs.setdefault(link.metric_id, []).append(link.transaction_id)
            if link.matched_keyword:
                keywords.setdefault(link.metric_id, {})[str(link.transaction_id)] = link.matched_keyword
    calls = (ExtractionCall.query.filter_by(extraction_id=row.id)
             .order_by(ExtractionCall.started_at, ExtractionCall.page_number).all())
    _log_view(row, actor)
    db.session.commit()
    return {**row.to_dict(), "label": types.label(row.declared_type),
            "fields": [f.to_dict() for f in fields], "pages": [p.to_dict() for p in pages],
            "transactions": [t.to_dict() for t in txns],
            "metrics": [m.to_dict(sorted(inputs.get(m.id, [])), keywords.get(m.id)) for m in metrics],
            "calls": [c.to_dict() for c in calls]}
