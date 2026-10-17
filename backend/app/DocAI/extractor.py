"""
Reading one document with the AI. Runs in the worker (job ai.extract_document),
never in a web request. Nothing but this module uses client.py.

    run_extraction(extraction_id)

1. Read the file through the document store (logged as action 'process').
2. Check the schema and prompt files are the ones the request named (SHA-256).
3. Prepare it (preprocess.py): a broken, locked or HEIC file → rescan_needed.
4. Ask the model: the whole file in one call, or (statements) one call per page.
   Every call is recorded with its tokens, cost and the raw response, encrypted.
   Busy / failing service: up to ai.max_attempts tries with growing pauses.
   An answer that fails the schema: one repair call with the errors, then failed.
5. Wrong document type or unreadable → rescan_needed, with the reason.
   Otherwise every value is stored with its confidence, page and checks
   (validators.py); a value that fails a check → needs_review.
   Statements: statements.py checks each page's arithmetic and computes metrics.

A failed extraction is never retried in place: staff retry (a new extraction) or
capture the details by hand.
"""
import json
import logging
import random
import time
import uuid
from decimal import Decimal

from flask import current_app

from app.database.database import db
from app.DocAI import guard, preprocess, schema_registry, types, validators
from app.DocAI.pricing import cost_usd
from app.DocAI.client import AIServiceError, ClaudeClient
from app.DocAI.model import (
    EXTRACTION_COMPLETED,
    EXTRACTION_FAILED,
    EXTRACTION_FINISHED,
    EXTRACTION_NEEDS_REVIEW,
    EXTRACTION_RESCAN,
    EXTRACTION_RUNNING,
    STATUS_LABELS,
    ExtractedField,
    Extraction,
    ExtractionCall,
)
from app.Documents import crypto
from app.Documents import service as documents
from app.Settings import business
from app.utils.audit_log import create_audit_log
from app.utils.dates import utcnow

logger = logging.getLogger(__name__)

PROCESSOR = "ai-worker"
BACKOFF_BASE_SECONDS = 2.0
MAX_RETRY_AFTER_SECONDS = 60.0
sleep = time.sleep  # tests replace it
_client_factory = None


class CallFailed(Exception):
    pass


def set_client_factory(factory) -> None:
    """Tests: build the client with a fake SDK. None restores the real one."""
    global _client_factory
    _client_factory = factory


def _client() -> ClaudeClient:
    if _client_factory is not None:
        return _client_factory()
    key = current_app.config.get("ANTHROPIC_API_KEY")
    if not key:
        raise CallFailed("The AI service isn't configured on the server (ANTHROPIC_API_KEY). Capture the details "
                         "by hand.")
    return ClaudeClient(key, float(current_app.config.get("AI_REQUEST_TIMEOUT_S") or 300))


def _backoff(attempt: int, retry_after: float | None) -> float:
    wait = BACKOFF_BASE_SECONDS * 2 ** (attempt - 1) + random.uniform(0, 1)
    if retry_after:
        wait = max(wait, min(retry_after, MAX_RETRY_AFTER_SECONDS))
    return wait


def _record(ex: Extraction, page: int | None, purpose: str, attempt: int, started, *, outcome: str,
            result=None, error: str | None = None, request_id: str | None = None,
            estimate: Decimal | None = None) -> None:
    """One row per API call, committed at once: the spend is real even if the job dies later.
    cost_usd is the ACTUAL cost from the returned token usage; the pre-call estimate is kept beside it."""
    call = ExtractionCall(id=uuid.uuid4(), extraction_id=ex.id, page_number=page, purpose=purpose, attempt=attempt,
                          model_requested=ex.model_requested, outcome=outcome, error=error, request_id=request_id,
                          started_at=started, finished_at=utcnow(), input_tokens=0, output_tokens=0,
                          cache_read_tokens=0, cache_write_tokens=0, estimated_cost_usd=estimate)
    if result is not None:
        call.model_returned = result.model
        call.request_id = result.request_id
        call.stop_reason = result.stop_reason
        call.latency_ms = result.latency_ms
        call.input_tokens, call.output_tokens = result.input_tokens, result.output_tokens
        call.cache_read_tokens, call.cache_write_tokens = result.cache_read_tokens, result.cache_write_tokens
        call.cost_usd = cost_usd(result.model or ex.model_requested, result.input_tokens, result.output_tokens,
                                 result.cache_read_tokens, result.cache_write_tokens)
        if call.cost_usd is None:
            call.cost_usd = cost_usd(ex.model_requested, result.input_tokens, result.output_tokens,
                                     result.cache_read_tokens, result.cache_write_tokens)
        sealed = crypto.seal(result.raw_json.encode("utf-8"), call.id.bytes, crypto.current_kek())
        call.raw_ciphertext, call.raw_nonce = sealed.ciphertext, sealed.nonce
        call.raw_wrapped_key, call.raw_key_id = sealed.wrapped_key, sealed.key_id
        ex.input_tokens += call.input_tokens
        ex.output_tokens += call.output_tokens
        ex.cache_read_tokens += call.cache_read_tokens
        ex.cache_write_tokens += call.cache_write_tokens
        ex.cost_usd = Decimal(ex.cost_usd or 0) + (call.cost_usd or 0)
    db.session.add(call)
    db.session.commit()
    guard.after_call(outcome)


def _parse(text: str | None, schema: dict) -> tuple[dict | None, list[str]]:
    if not text:
        return None, ["The answer was empty."]
    try:
        obj = json.loads(text)
    except ValueError as e:
        return None, [f"The answer isn't valid JSON: {e}"]
    return obj, schema_registry.validate(schema, obj)


def ask(ex: Extraction, client: ClaudeClient, system: str, content: list, schema: dict, api_schema: dict,
        page: int | None = None) -> dict:
    """One model answer that passes the schema, or CallFailed with the reason staff will see.
    Every call (retries and repairs too) first passes the kill switch, breaker and budgets (guard.py)."""
    max_attempts = int(business.get("ai.max_attempts"))
    messages = [{"role": "user", "content": content}]
    purpose, attempt = "extract", 0
    while True:
        attempt += 1
        try:
            estimate = guard.check_before_call(ex, 1 if page is not None else (ex.page_count or 1), page)
        except guard.Refused as e:
            raise CallFailed(str(e))
        started = utcnow()
        try:
            result = client.read(model=ex.model_requested, effort=ex.effort, system=system, messages=messages,
                                 schema=api_schema)
        except AIServiceError as e:
            _record(ex, page, purpose, attempt, started, outcome="retryable_error" if e.retryable else
                    "permanent_error", error=str(e), request_id=e.request_id, estimate=estimate)
            if not e.retryable:
                raise CallFailed(f"The AI service refused the request ({e}). Capture the details by hand, or "
                                 "retry after it is fixed.")
            if attempt >= max_attempts:
                raise CallFailed(f"The AI service didn't respond after {attempt} tries ({e}). Retry later, or "
                                 "capture the details by hand.")
            sleep(_backoff(attempt, e.retry_after))
            continue
        if result.stop_reason == "refusal":
            _record(ex, page, purpose, attempt, started, outcome="refusal", result=result,
                    error="The model declined to answer.", estimate=estimate)
            raise CallFailed("The AI declined to read this document. Capture the details by hand.")
        obj, errors = _parse(result.text, schema)
        if result.stop_reason == "max_tokens":
            errors = ["The answer was cut off (too long)."] + errors
        if not errors:
            _record(ex, page, purpose, attempt, started, outcome="ok", result=result, estimate=estimate)
            return obj
        _record(ex, page, purpose, attempt, started, outcome="invalid_output", result=result,
                error="; ".join(errors)[:2000], estimate=estimate)
        if purpose == "repair" or result.stop_reason == "max_tokens":
            raise CallFailed("The AI's answer didn't match the expected format"
                             + (" (it was too long)" if result.stop_reason == "max_tokens" else ", twice")
                             + ". Capture the details by hand.")
        # One repair (05 ADR-05-3): show the model its answer and what is wrong with it.
        messages = messages + [
            {"role": "assistant", "content": result.text or ""},
            {"role": "user", "content": "That answer doesn't match the required format:\n- "
                                        + "\n- ".join(errors[:10])
                                        + "\nReturn the corrected answer for the same document."},
        ]
        purpose, attempt = "repair", 0


def finish(ex: Extraction, status: str, reason: str | None = None) -> None:
    ex.status, ex.status_reason, ex.finished_at = status, reason, utcnow()
    create_audit_log("AI_EXTRACTION_FINISHED", target_type="ai_extraction", target_id=ex.id,
                     target_name=ex.declared_type,
                     description=f"{STATUS_LABELS[status]}" + (f": {reason}" if reason else ""),
                     new_value={"status": status, "pages": ex.page_count, "cost_usd": str(ex.cost_usd),
                                "input_tokens": ex.input_tokens, "output_tokens": ex.output_tokens},
                     actor_user_email="scheduler", actor_user_name=PROCESSOR)


def check_identity(ex: Extraction, detected: str, readable: bool, unreadable_reason: str | None,
                   where: str = "") -> str | None:
    """The rescan reason if the answer says the document is the wrong type or can't be read."""
    if not readable:
        return (f"The scan{where} can't be read: {(unreadable_reason or 'no reason given').rstrip('.')}. "
                "Upload a clearer copy, or capture the details by hand.")
    if detected != ex.declared_type:
        return (f"This{where} looks like {_a(types.label(detected))}, not {_a(types.label(ex.declared_type))}. "
                "Upload the right document (or correct its type), or capture the details by hand.")
    return None


def _a(text: str) -> str:
    if text.startswith("a "):
        return text
    return ("an " if text[:1].lower() in "aeiou" or text.startswith("M-") else "a ") + text


def store_field(ex: Extraction, path: str, kind: str, entry: dict, page_count: int | None,
                page_override: int | None = None) -> ExtractedField:
    entry = dict(entry or {})
    if page_override is not None:
        entry["source_page"] = page_override
    validation, reason = validators.validate_field(kind, entry, page_count)
    value = entry.get("value")
    confidence = entry.get("confidence")
    row = ExtractedField(
        extraction_id=ex.id, field_path=path[:120], value=None if value is None else str(value),
        confidence=None if confidence is None else Decimal(str(confidence)).quantize(Decimal("0.001")),
        source_page=entry.get("source_page"), source_text=(entry.get("source_text") or None) and
        str(entry["source_text"])[:200], legibility=entry.get("legibility"), notes=entry.get("notes"),
        validation=validation, validation_reason=reason)
    db.session.add(row)
    return row


def _store_document(ex: Extraction, t: types.DocType, answer: dict) -> None:
    ex.detected_document_type = answer["detected_document_type"]
    ex.readable = answer["readable"]
    ex.warnings = list(answer.get("warnings") or []) or None
    rescan = check_identity(ex, ex.detected_document_type, ex.readable, answer.get("unreadable_reason"))
    if rescan:
        return finish(ex, EXTRACTION_RESCAN, rescan)
    fields = answer["fields"]
    stored = [store_field(ex, f.name, f.kind, fields[f.name], ex.page_count) for f in t.fields]
    for group, items in t.lists.items():
        for i, item in enumerate(fields.get(group) or []):
            stored += [store_field(ex, f"{group}[{i}].{f.name}", f.kind, item[f.name], ex.page_count) for f in items]
    failed = [f for f in stored if f.validation == "failed"]
    if failed:
        listed = "; ".join(f"{f.field_path} ({f.validation_reason})" for f in failed[:5])
        return finish(ex, EXTRACTION_NEEDS_REVIEW, f"{len(failed)} value(s) failed checks: {listed}")
    finish(ex, EXTRACTION_COMPLETED)


def intro(t: types.DocType, page_count: int, page: int | None = None) -> str:
    if page is None:
        return (f"The attached file was uploaded as {_a(t.label)}. It has {page_count} page(s). "
                "Read it as instructed and answer in the required format.")
    return (f"The attached file is page {page} of {page_count} of a document uploaded as {_a(t.label)}. "
            f"Report page_number {page}. Read it as instructed and answer in the required format.")


def run_extraction(extraction_id: int) -> dict:
    ex = db.session.query(Extraction).filter_by(id=extraction_id).with_for_update().one_or_none()
    if ex is None:
        return {"skipped": "not found"}
    if ex.status in EXTRACTION_FINISHED:
        return {"skipped": ex.status}  # already done (e.g. a re-run job after a worker died)
    ex.status, ex.started_at = EXTRACTION_RUNNING, utcnow()
    db.session.commit()
    try:
        _run(ex)
    except Exception:
        logger.exception("AI extraction %s failed unexpectedly", extraction_id)
        db.session.rollback()
        ex = db.session.get(Extraction, extraction_id)
        finish(ex, EXTRACTION_FAILED, "Something went wrong while reading this document. Retry, or capture the "
                                      "details by hand.")
    db.session.commit()
    return {"extraction_id": ex.id, "status": ex.status}


def _run(ex: Extraction) -> None:
    t = types.get(ex.declared_type)
    try:
        doc, data = documents.read_for_processing(ex.document_id, PROCESSOR, ("ai_extraction", str(ex.id)))
    except documents.Gone:
        return finish(ex, EXTRACTION_FAILED, "The document was destroyed before it could be read.")
    schema, _, schema_sha = schema_registry.load(t)
    system, _, prompt_sha = schema_registry.load_prompt(t)
    if doc.sha256 != ex.document_sha256 or schema_sha != ex.schema_sha256 or prompt_sha != ex.prompt_sha256:
        return finish(ex, EXTRACTION_FAILED, "The document, schema or prompt changed since this reading was "
                                             "requested. Request a new one.")
    try:
        prepared = preprocess.prepare(doc.content_type, data)
    except preprocess.RescanNeeded as e:
        return finish(ex, EXTRACTION_RESCAN, str(e))
    ex.page_count = prepared.page_count
    api_schema = schema_registry.for_api(schema)
    try:
        client = _client()
        if t.statement:
            from app.DocAI import statements
            return statements.read(ex, t, prepared, client, system, schema, api_schema)
        answer = ask(ex, client, system, [prepared.whole, {"type": "text", "text": intro(t, prepared.page_count)}],
                     schema, api_schema)
    except CallFailed as e:
        return finish(ex, EXTRACTION_FAILED, str(e))
    _store_document(ex, t, answer)
