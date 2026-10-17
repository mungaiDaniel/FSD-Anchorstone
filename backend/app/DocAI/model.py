"""
AI document extraction records (phase 3a; 05-ai-document-pipeline §10).

    ai_extractions              one per request to read a document. The model, prompt and
                                schema versions and the document's SHA-256 are fixed when
                                it is requested; a re-extraction is a new row (supersedes_id)
    ai_extraction_calls         every API call: tokens, cost, request id, model returned and
                                the raw response, encrypted under DOCUMENT_KEK
    ai_extracted_fields         each value read, with confidence, source page and validation
    ai_statement_pages          statements: per-page balance check done in Python
    ai_statement_transactions   statements: the rows the model listed
    ai_statement_metrics        statements: figures computed in Python, linked to their rows
                                through ai_statement_metric_inputs

Nothing here is edited or deleted (database triggers). An extraction changes status
until it finishes; after that it is frozen too.
"""
import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID

from app.database.database import db
from app.utils.dates import iso
from app.utils.money import as_str
from base_model import Base

EXTRACTION_QUEUED = "queued"
EXTRACTION_RUNNING = "running"
EXTRACTION_COMPLETED = "completed"
EXTRACTION_NEEDS_REVIEW = "needs_review"
EXTRACTION_RESCAN = "rescan_needed"
EXTRACTION_FAILED = "failed"
EXTRACTION_STATUSES = (EXTRACTION_QUEUED, EXTRACTION_RUNNING, EXTRACTION_COMPLETED, EXTRACTION_NEEDS_REVIEW,
                       EXTRACTION_RESCAN, EXTRACTION_FAILED)
EXTRACTION_FINISHED = (EXTRACTION_COMPLETED, EXTRACTION_NEEDS_REVIEW, EXTRACTION_RESCAN, EXTRACTION_FAILED)
STATUS_LABELS = {EXTRACTION_QUEUED: "Queued", EXTRACTION_RUNNING: "Reading", EXTRACTION_COMPLETED: "Read",
                 EXTRACTION_NEEDS_REVIEW: "Needs review", EXTRACTION_RESCAN: "Rescan needed",
                 EXTRACTION_FAILED: "Extraction failed"}

CALL_OUTCOMES = ("ok", "invalid_output", "refusal", "retryable_error", "permanent_error")
FIELD_VALIDATIONS = ("passed", "failed", "empty")
PAGE_BALANCED = "balanced"
PAGE_NEEDS_REVIEW = "needs_review"
PAGE_RESCAN = "rescan_needed"
PAGE_STATUSES = (PAGE_BALANCED, PAGE_NEEDS_REVIEW, PAGE_RESCAN)
METRIC_UNITS = ("KES", "ratio", "count", "months")


def _in(column: str, values) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class Extraction(Base, db.Model):
    __tablename__ = "ai_extractions"
    __table_args__ = (
        CheckConstraint(_in("status", EXTRACTION_STATUSES), name="ck_ai_extractions_status"),
        CheckConstraint("(status IN ('queued', 'running')) = (finished_at IS NULL)", name="ck_ai_extractions_finished"),
        CheckConstraint("status NOT IN ('needs_review', 'rescan_needed', 'failed') OR status_reason IS NOT NULL",
                        name="ck_ai_extractions_reason"),
        CheckConstraint("char_length(document_sha256) = 64 AND char_length(prompt_sha256) = 64 "
                        "AND char_length(schema_sha256) = 64", name="ck_ai_extractions_hashes"),
        CheckConstraint("cost_usd >= 0", name="ck_ai_extractions_cost"),
        Index("ix_ai_extractions_document", "document_id", "requested_at"),
    )

    id = Column(Integer, primary_key=True)
    party_id = Column(Integer, ForeignKey("parties.id", ondelete="RESTRICT"), nullable=False, index=True)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="RESTRICT"), nullable=False)
    declared_type = Column(String(50), nullable=False)
    status = Column(String(16), nullable=False, default=EXTRACTION_QUEUED, server_default=EXTRACTION_QUEUED)
    status_reason = Column(Text, nullable=True)
    detected_document_type = Column(String(50), nullable=True)
    readable = Column(Boolean, nullable=True)
    page_count = Column(Integer, nullable=True)
    # Fixed when requested, so a re-run of the same row reads the same way (AI-10).
    model_requested = Column(String(80), nullable=False)
    effort = Column(String(10), nullable=False)
    prompt_version = Column(String(40), nullable=False)
    prompt_sha256 = Column(String(64), nullable=False)
    schema_version = Column(String(40), nullable=False)
    schema_sha256 = Column(String(64), nullable=False)
    document_sha256 = Column(String(64), nullable=False)
    input_tokens = Column(Integer, nullable=False, default=0, server_default="0")
    output_tokens = Column(Integer, nullable=False, default=0, server_default="0")
    cache_read_tokens = Column(Integer, nullable=False, default=0, server_default="0")
    cache_write_tokens = Column(Integer, nullable=False, default=0, server_default="0")
    cost_usd = Column(Numeric(12, 6), nullable=False, default=0, server_default="0")
    supersedes_id = Column(Integer, ForeignKey("ai_extractions.id", ondelete="RESTRICT"), nullable=True)
    job_id = Column(Integer, ForeignKey("jobs.id", ondelete="RESTRICT"), nullable=True)
    requested_by = Column(String(120), nullable=False)
    requested_at = Column(DateTime(timezone=True), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "party_id": self.party_id, "document_id": str(self.document_id),
            "declared_type": self.declared_type, "status": self.status,
            "status_label": STATUS_LABELS[self.status], "status_reason": self.status_reason,
            "detected_document_type": self.detected_document_type, "readable": self.readable,
            "page_count": self.page_count, "model_requested": self.model_requested, "effort": self.effort,
            "prompt_version": self.prompt_version, "prompt_sha256": self.prompt_sha256,
            "schema_version": self.schema_version, "schema_sha256": self.schema_sha256,
            "document_sha256": self.document_sha256, "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens, "cache_read_tokens": self.cache_read_tokens,
            "cache_write_tokens": self.cache_write_tokens, "cost_usd": str(self.cost_usd),
            "supersedes_id": self.supersedes_id, "job_id": self.job_id, "requested_by": self.requested_by,
            "requested_at": iso(self.requested_at), "started_at": iso(self.started_at),
            "finished_at": iso(self.finished_at),
        }


class ExtractionCall(Base, db.Model):
    __tablename__ = "ai_extraction_calls"
    __table_args__ = (
        CheckConstraint(_in("outcome", CALL_OUTCOMES), name="ck_ai_extraction_calls_outcome"),
        CheckConstraint("purpose IN ('extract', 'repair')", name="ck_ai_extraction_calls_purpose"),
        CheckConstraint("(raw_ciphertext IS NULL) = (raw_wrapped_key IS NULL)", name="ck_ai_extraction_calls_raw"),
        CheckConstraint("attempt >= 1", name="ck_ai_extraction_calls_attempt"),
        Index("ix_ai_extraction_calls_extraction", "extraction_id", "started_at"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    extraction_id = Column(Integer, ForeignKey("ai_extractions.id", ondelete="RESTRICT"), nullable=False)
    page_number = Column(Integer, nullable=True)  # NULL = the whole document in one call
    purpose = Column(String(10), nullable=False, default="extract")
    attempt = Column(Integer, nullable=False)
    model_requested = Column(String(80), nullable=False)
    model_returned = Column(String(80), nullable=True)  # as reported by the API (differs after a fallback)
    request_id = Column(String(120), nullable=True)
    input_tokens = Column(Integer, nullable=False, default=0)
    output_tokens = Column(Integer, nullable=False, default=0)
    cache_read_tokens = Column(Integer, nullable=False, default=0)
    cache_write_tokens = Column(Integer, nullable=False, default=0)
    cost_usd = Column(Numeric(12, 6), nullable=True)  # NULL when the model has no price in ai.price_table
    latency_ms = Column(Integer, nullable=True)
    stop_reason = Column(String(30), nullable=True)
    outcome = Column(String(16), nullable=False)
    error = Column(Text, nullable=True)
    raw_ciphertext = Column(LargeBinary, nullable=True)
    raw_nonce = Column(LargeBinary, nullable=True)
    raw_wrapped_key = Column(LargeBinary, nullable=True)
    raw_key_id = Column(String(50), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=False)
    finished_at = Column(DateTime(timezone=True), nullable=False)

    def to_dict(self) -> dict:
        """Never includes the raw response (it holds the client's personal data)."""
        return {
            "id": str(self.id), "page_number": self.page_number, "purpose": self.purpose, "attempt": self.attempt,
            "model_requested": self.model_requested, "model_returned": self.model_returned,
            "request_id": self.request_id, "input_tokens": self.input_tokens, "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens, "cache_write_tokens": self.cache_write_tokens,
            "cost_usd": None if self.cost_usd is None else str(self.cost_usd), "latency_ms": self.latency_ms,
            "stop_reason": self.stop_reason, "outcome": self.outcome, "error": self.error,
            "raw_stored": self.raw_ciphertext is not None, "started_at": iso(self.started_at),
            "finished_at": iso(self.finished_at),
        }


class ExtractedField(Base, db.Model):
    __tablename__ = "ai_extracted_fields"
    __table_args__ = (
        CheckConstraint(_in("validation", FIELD_VALIDATIONS), name="ck_ai_extracted_fields_validation"),
        CheckConstraint("confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
                        name="ck_ai_extracted_fields_confidence"),
        UniqueConstraint("extraction_id", "field_path", name="uq_ai_extracted_fields_path"),
    )

    id = Column(Integer, primary_key=True)
    extraction_id = Column(Integer, ForeignKey("ai_extractions.id", ondelete="RESTRICT"), nullable=False)
    field_path = Column(String(120), nullable=False)
    value = Column(Text, nullable=True)
    confidence = Column(Numeric(4, 3), nullable=True)
    source_page = Column(Integer, nullable=True)
    source_text = Column(String(200), nullable=True)
    legibility = Column(String(12), nullable=True)
    notes = Column(Text, nullable=True)
    validation = Column(String(10), nullable=False)
    validation_reason = Column(Text, nullable=True)

    def to_dict(self) -> dict:
        return {"path": self.field_path, "value": self.value,
                "confidence": None if self.confidence is None else str(self.confidence),
                "source_page": self.source_page, "source_text": self.source_text, "legibility": self.legibility,
                "notes": self.notes, "validation": self.validation, "validation_reason": self.validation_reason}


class StatementPage(Base, db.Model):
    __tablename__ = "ai_statement_pages"
    __table_args__ = (
        CheckConstraint(_in("status", PAGE_STATUSES), name="ck_ai_statement_pages_status"),
        CheckConstraint("status = 'balanced' OR reason IS NOT NULL", name="ck_ai_statement_pages_reason"),
        UniqueConstraint("extraction_id", "page_number", name="uq_ai_statement_pages_page"),
    )

    id = Column(Integer, primary_key=True)
    extraction_id = Column(Integer, ForeignKey("ai_extractions.id", ondelete="RESTRICT"), nullable=False)
    page_number = Column(Integer, nullable=False)
    status = Column(String(14), nullable=False)
    opening_balance = Column(Numeric(20, 2), nullable=True)
    closing_balance = Column(Numeric(20, 2), nullable=True)
    credits_total = Column(Numeric(20, 2), nullable=True)
    debits_total = Column(Numeric(20, 2), nullable=True)
    computed_closing = Column(Numeric(20, 2), nullable=True)
    difference = Column(Numeric(20, 2), nullable=True)  # computed − printed closing
    transaction_count = Column(Integer, nullable=False, default=0)
    reason = Column(Text, nullable=True)

    def to_dict(self) -> dict:
        return {"page_number": self.page_number, "status": self.status,
                "opening_balance": as_str(self.opening_balance), "closing_balance": as_str(self.closing_balance),
                "credits_total": as_str(self.credits_total), "debits_total": as_str(self.debits_total),
                "computed_closing": as_str(self.computed_closing), "difference": as_str(self.difference),
                "transaction_count": self.transaction_count, "reason": self.reason}


class StatementTransaction(Base, db.Model):
    __tablename__ = "ai_statement_transactions"
    __table_args__ = (
        CheckConstraint("debit IS NULL OR debit >= 0", name="ck_ai_statement_transactions_debit"),
        CheckConstraint("credit IS NULL OR credit >= 0", name="ck_ai_statement_transactions_credit"),
        UniqueConstraint("extraction_id", "page_number", "row_no", name="uq_ai_statement_transactions_row"),
    )

    id = Column(Integer, primary_key=True)
    extraction_id = Column(Integer, ForeignKey("ai_extractions.id", ondelete="RESTRICT"), nullable=False)
    page_number = Column(Integer, nullable=False)
    row_no = Column(Integer, nullable=False)  # 1-based, oldest first on the page
    txn_date = Column(Date, nullable=True)
    description = Column(Text, nullable=True)
    reference = Column(String(120), nullable=True)
    debit = Column(Numeric(20, 2), nullable=True)
    credit = Column(Numeric(20, 2), nullable=True)
    balance = Column(Numeric(20, 2), nullable=True)
    confidence = Column(Numeric(4, 3), nullable=True)

    def to_dict(self) -> dict:
        return {"id": self.id, "page_number": self.page_number, "row_no": self.row_no, "date": iso(self.txn_date),
                "description": self.description, "reference": self.reference, "debit": as_str(self.debit),
                "credit": as_str(self.credit), "balance": as_str(self.balance),
                "confidence": None if self.confidence is None else str(self.confidence)}


class StatementMetric(Base, db.Model):
    __tablename__ = "ai_statement_metrics"
    __table_args__ = (
        CheckConstraint(_in("unit", METRIC_UNITS), name="ck_ai_statement_metrics_unit"),
        UniqueConstraint("extraction_id", "metric", name="uq_ai_statement_metrics_metric"),
    )

    id = Column(Integer, primary_key=True)
    extraction_id = Column(Integer, ForeignKey("ai_extractions.id", ondelete="RESTRICT"), nullable=False)
    metric = Column(String(60), nullable=False)
    value = Column(Numeric(20, 4), nullable=False)
    unit = Column(String(8), nullable=False)
    period_from = Column(Date, nullable=True)
    period_to = Column(Date, nullable=True)
    definition = Column(Text, nullable=False)  # how it was computed, in words (with the keywords used)

    def to_dict(self, input_ids: list[int] | None = None) -> dict:
        value = self.value
        if self.unit == "KES":
            value = as_str(value)
        elif self.unit in ("count", "months"):
            value = str(int(value))
        else:
            value = str(value)
        return {"metric": self.metric, "value": value, "unit": self.unit, "period_from": iso(self.period_from),
                "period_to": iso(self.period_to), "definition": self.definition,
                "transaction_ids": input_ids if input_ids is not None else []}


class StatementMetricInput(db.Model):
    __tablename__ = "ai_statement_metric_inputs"

    metric_id = Column(Integer, ForeignKey("ai_statement_metrics.id", ondelete="RESTRICT"), primary_key=True)
    transaction_id = Column(Integer, ForeignKey("ai_statement_transactions.id", ondelete="RESTRICT"),
                            primary_key=True)
