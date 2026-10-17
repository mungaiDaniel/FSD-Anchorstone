"""
Staff review of an AI reading, with maker-checker (AI-07; 05 §8).

    detail(extraction_id, actor)        values with confidence and page, low-confidence ones
                                        flagged (ai.review.confidence_threshold); statement
                                        pages that don't balance first
    set_field(…)                        accept / correct / not present. A correction is stored
                                        beside the AI value (field_reviews); the AI value is
                                        never changed
    set_transaction(…)                  a corrected statement row (transaction_reviews); the
                                        page is re-checked in Python on the reviewed rows
    mark_unreliable(…)                  a statement that can't be fixed: its rules then see
                                        missing data
    submit(…)                           every value has an action and every statement page
                                        balances (or it is marked unreliable) → change request
                                        ai.review, approved by a different person

On approval (AIReviewApproval.apply) the confirmed values fill the client's record where
it is empty — never overwriting (a difference shows as a cross-check instead) — and a
statement's metrics are recomputed from the reviewed rows. Only approved reviews feed
the cross-checks and the rules.
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.Applications.model import ExtractionReview, FieldReview, LoanApplication, TransactionReview
from app.Approvals import service as approvals
from app.Approvals.handlers import Handler, register
from app.Approvals.model import CR_APPLIED, CR_OPEN, CR_RETURNED, ChangeRequest
from app.database.database import db
from app.DocAI import metrics, types, validators
from app.DocAI.model import (
    EXTRACTION_COMPLETED,
    EXTRACTION_NEEDS_REVIEW,
    PAGE_BALANCED,
    PAGE_RESCAN,
    ExtractedField,
    Extraction,
    StatementPage,
    StatementTransaction,
)
from app.DocAI.statements import Row, check_page
from app.Documents.model import DataAccessLog
from app.Parties import service as parties
from app.Parties.model import Party, PartyIdentifier, PartyOrganisation, PartyPerson
from app.Parties.normalise import ID_TYPE_LABELS, normalise_identifier
from app.Settings import business
from app.utils.audit_log import create_audit_log, get_client_ip
from app.utils.dates import parse_date, utcnow
from app.utils.http import Conflict, NotFound, ValidationError
from app.utils.money import as_str

REVIEWABLE = (EXTRACTION_COMPLETED, EXTRACTION_NEEDS_REVIEW)
# What an approved review may write to the client's record (only where it is empty).
IDENTIFIER_FIELDS = {("national_id", "id_number"): "national_id", ("passport", "passport_number"): "passport",
                     ("kra_pin", "kra_pin"): "kra_pin",
                     ("certificate_of_incorporation", "registration_number"): "company_reg_no",
                     ("cr12", "registration_number"): "company_reg_no"}
DATE_FIELDS = {("national_id", "date_of_birth"): (PartyPerson, "date_of_birth"),
               ("passport", "date_of_birth"): (PartyPerson, "date_of_birth"),
               ("certificate_of_incorporation", "registration_date"): (PartyOrganisation, "registration_date")}


# ── Reading the state of a review ──


def _extraction(extraction_id: int) -> Extraction:
    ex = db.session.get(Extraction, extraction_id)
    if ex is None:
        raise NotFound("Extraction not found.")
    return ex


def get_review(extraction_id: int) -> ExtractionReview | None:
    return ExtractionReview.query.filter_by(extraction_id=extraction_id).one_or_none()


def state(review: ExtractionReview | None) -> str:
    """draft / submitted / returned / approved / rejected (from the change request)."""
    if review is None or review.change_request_id is None:
        return "draft"
    if review.approved_at is not None:
        return "approved"
    cr = db.session.get(ChangeRequest, review.change_request_id)
    return {"pending": "submitted", "returned": "returned", "applied": "approved"}.get(cr.status, "rejected")


def is_approved(review: ExtractionReview | None) -> bool:
    return review is not None and review.approved_at is not None


def _editable(review: ExtractionReview) -> None:
    if state(review) in ("submitted", "approved"):
        raise Conflict("This review was submitted for approval and can't be changed now.")


def _open(extraction_id: int, actor, application_id: int | None = None) -> ExtractionReview:
    ex = _extraction(extraction_id)
    if ex.status not in REVIEWABLE:
        raise Conflict("Only a reading that finished (read, or read with values to check) can be reviewed. "
                       "Rescan, retry or capture the details by hand.")
    review = get_review(ex.id)
    if review is None:
        review = ExtractionReview(extraction_id=ex.id, application_id=application_id, reviewed_by=actor.email)
        db.session.add(review)
        db.session.flush()
    return review


def threshold() -> Decimal:
    return Decimal(business.get("ai.review.confidence_threshold"))


@dataclass
class Reviewed:
    """A statement row as reviewed (the correction where there is one, else the AI value)."""
    id: int
    page_number: int
    row_no: int
    txn_date: date | None
    description: str | None
    debit: Decimal | None
    credit: Decimal | None
    balance: Decimal | None
    corrected: bool


def reviewed_rows(ex: Extraction, review: ExtractionReview | None) -> list[Reviewed]:
    corrections = {t.transaction_id: t for t in TransactionReview.query.filter_by(review_id=review.id)} \
        if review else {}
    out = []
    for t in (StatementTransaction.query.filter_by(extraction_id=ex.id)
              .order_by(StatementTransaction.page_number, StatementTransaction.row_no)):
        c = corrections.get(t.id)
        out.append(Reviewed(t.id, t.page_number, t.row_no, c.txn_date if c else t.txn_date, t.description,
                            c.debit if c else t.debit, c.credit if c else t.credit, c.balance if c else t.balance,
                            c is not None))
    return out


def page_checks(ex: Extraction, review: ExtractionReview | None) -> list[dict]:
    """Each page re-checked on the reviewed rows. Pages that don't balance come first."""
    rows = reviewed_rows(ex, review)
    out = []
    for page in StatementPage.query.filter_by(extraction_id=ex.id).order_by(StatementPage.page_number):
        mine = [r for r in rows if r.page_number == page.page_number]
        if page.status == PAGE_RESCAN:
            out.append({**page.to_dict(), "reviewed_status": PAGE_RESCAN, "reviewed_reason": page.reason})
            continue
        result = check_page([Row(r.row_no, r.txn_date, r.description, None, r.debit, r.credit, r.balance, None)
                             for r in mine], page.opening_balance, page.closing_balance, None)
        out.append({**page.to_dict(), "reviewed_status": result.status, "reviewed_difference": as_str(result.difference),
                    "reviewed_reason": " ".join(result.problems) or None,
                    "corrected_rows": sum(1 for r in mine if r.corrected)})
    out.sort(key=lambda p: (p["reviewed_status"] == PAGE_BALANCED, p["page_number"]))
    return out


def confirmed_values(ex: Extraction, review: ExtractionReview | None) -> dict[str, str | None]:
    """field path → the confirmed value (accepted AI value, or the correction; None when not present)."""
    out = {}
    actions = {f.field_id: f for f in FieldReview.query.filter_by(review_id=review.id)} if review else {}
    for f in ExtractedField.query.filter_by(extraction_id=ex.id):
        a = actions.get(f.id)
        if a is None:
            continue
        out[f.field_path] = f.value if a.action == "accept" else a.corrected_value if a.action == "correct" else None
    return out


def _log_view(ex: Extraction, actor) -> None:
    from flask import has_request_context, request
    db.session.add(DataAccessLog(user_id=actor.id, user_email=actor.email, document_id=ex.document_id,
                                 entity_type="ai_extraction", entity_id=str(ex.id), action="view",
                                 ip_address=get_client_ip() if has_request_context() else None,
                                 user_agent=(request.headers.get("User-Agent") or "")[:255]
                                 if has_request_context() else None, at=utcnow()))


def detail(extraction_id: int, actor) -> dict:
    ex = _extraction(extraction_id)
    review = get_review(ex.id)
    limit = threshold()
    actions = {f.field_id: f for f in FieldReview.query.filter_by(review_id=review.id)} if review else {}
    fields = []
    for f in ExtractedField.query.filter_by(extraction_id=ex.id).order_by(ExtractedField.id):
        a = actions.get(f.id)
        low = f.confidence is None or f.confidence < limit
        fields.append({**f.to_dict(), "id": f.id, "low_confidence": low,
                       "review": None if a is None else {"action": a.action, "corrected_value": a.corrected_value,
                                                         "reason": a.reason, "reviewed_by": a.reviewed_by}})
    # Values that failed a check, then low confidence, then the rest (05 §8).
    fields.sort(key=lambda f: (f["validation"] != "failed", not f["low_confidence"]))
    t = types.get(ex.declared_type)
    corrections = {c.transaction_id: c for c in TransactionReview.query.filter_by(review_id=review.id)} \
        if review else {}
    txns = []
    for row in (StatementTransaction.query.filter_by(extraction_id=ex.id)
                .order_by(StatementTransaction.page_number, StatementTransaction.row_no)):
        c = corrections.get(row.id)
        txns.append({**row.to_dict(), "low_confidence": row.confidence is not None and row.confidence < limit,
                     "review": None if c is None else {"date": c.txn_date.isoformat() if c.txn_date else None,
                                                       "debit": as_str(c.debit), "credit": as_str(c.credit),
                                                       "balance": as_str(c.balance), "reason": c.reason,
                                                       "reviewed_by": c.reviewed_by}})
    from app.Documents.model import Document

    doc = db.session.get(Document, ex.document_id)
    _log_view(ex, actor)
    db.session.commit()
    return {"extraction": {**ex.to_dict(), "label": types.label(ex.declared_type)},
            "document": {"id": str(doc.id), "filename": doc.original_filename, "content_type": doc.content_type},
            "statement": bool(t and t.statement), "confidence_threshold": str(limit),
            "review": None if review is None else {
                "id": review.id, "state": state(review), "reviewed_by": review.reviewed_by,
                "submitted_at": review.submitted_at.isoformat() if review.submitted_at else None,
                "approved_by": review.approved_by, "change_request_id": review.change_request_id,
                "statement_unreliable": review.statement_unreliable, "unreliable_reason": review.unreliable_reason,
                "confirmed_metrics": review.confirmed_metrics, "party_updates": review.party_updates},
            "state": state(review), "fields": fields, "pages": page_checks(ex, review) if t and t.statement else [],
            "transactions": txns, "missing_actions": _missing(ex, review)}


def _missing(ex: Extraction, review: ExtractionReview | None) -> int:
    done = {f.field_id for f in FieldReview.query.filter_by(review_id=review.id)} if review else set()
    q = ExtractedField.query.filter(ExtractedField.extraction_id == ex.id)
    if done:
        q = q.filter(ExtractedField.id.notin_(done))
    return q.count()


# ── The reviewer's actions ──


def _kind(ex: Extraction, field_path: str) -> str:
    t = types.get(ex.declared_type)
    path = field_path.removeprefix("header.")
    if "[" in path:
        group, rest = path.split("[", 1)
        path = f"{group}[].{rest.split('].', 1)[1]}"
    return t.kinds().get(path, "text") if t else "text"


def set_field(extraction_id: int, field_id: int, data: dict, actor, application_id: int | None = None) -> FieldReview:
    review = _open(extraction_id, actor, application_id)
    _editable(review)
    field = db.session.get(ExtractedField, field_id)
    if field is None or field.extraction_id != review.extraction_id:
        raise NotFound("Field not found in this reading.")
    action = str(data.get("action") or "").strip()
    if action not in ("accept", "correct", "not_present"):
        raise ValidationError("action must be accept, correct or not_present.")
    value = reason = None
    if action == "accept" and (field.value is None or field.validation == "failed"):
        raise ValidationError("A value that is missing or failed its check can't be accepted as read: correct it "
                              "or mark it not present.")
    if action == "correct":
        value = " ".join(str(data.get("value") or "").split())
        reason = " ".join(str(data.get("reason") or "").split())
        if not value:
            raise ValidationError("Enter the corrected value.")
        if not reason:
            raise ValidationError("A reason is required for a correction.")
        problem = validators.check(_kind(review_extraction(review), field.field_path), value)
        if problem:
            raise ValidationError(f"The corrected value isn't valid: {problem}")
        if value == (field.value or ""):
            raise ValidationError("The correction is the same as the value read; accept it instead.")
    row = FieldReview.query.filter_by(review_id=review.id, field_id=field.id).one_or_none()
    if row is None:
        row = FieldReview(review_id=review.id, field_id=field.id)
        db.session.add(row)
    row.action, row.corrected_value, row.reason = action, value, reason
    row.reviewed_by, row.reviewed_at = actor.email, utcnow()
    db.session.commit()
    return row


def review_extraction(review: ExtractionReview) -> Extraction:
    return db.session.get(Extraction, review.extraction_id)


def _amount(data: dict, key: str, signed: bool = False) -> Decimal | None:
    raw = data.get(key)
    if raw in (None, ""):
        return None
    value = validators.parse_money(str(raw), signed=signed)
    if value is None:
        raise ValidationError(f"{key} must be an amount with at most 2 decimal places.")
    return value


def set_transaction(extraction_id: int, transaction_id: int, data: dict, actor,
                    application_id: int | None = None) -> TransactionReview:
    review = _open(extraction_id, actor, application_id)
    _editable(review)
    txn = db.session.get(StatementTransaction, transaction_id)
    if txn is None or txn.extraction_id != review.extraction_id:
        raise NotFound("Row not found in this statement.")
    reason = " ".join(str(data.get("reason") or "").split())
    if not reason:
        raise ValidationError("A reason is required for a correction.")
    debit, credit, balance = _amount(data, "debit"), _amount(data, "credit"), _amount(data, "balance", signed=True)
    if debit is None and credit is None:
        raise ValidationError("A row needs a debit or a credit.")
    when = parse_date(data.get("date"), "date", required=False)
    row = TransactionReview.query.filter_by(review_id=review.id, transaction_id=txn.id).one_or_none()
    if row is None:
        row = TransactionReview(review_id=review.id, transaction_id=txn.id)
        db.session.add(row)
    row.txn_date, row.debit, row.credit, row.balance = when or txn.txn_date, debit, credit, balance
    row.reason, row.reviewed_by, row.reviewed_at = reason, actor.email, utcnow()
    db.session.commit()
    return row


def mark_unreliable(extraction_id: int, data: dict, actor, application_id: int | None = None) -> ExtractionReview:
    review = _open(extraction_id, actor, application_id)
    _editable(review)
    t = types.get(review_extraction(review).declared_type)
    if not (t and t.statement):
        raise ValidationError("Only a statement can be marked not reliable.")
    reason = " ".join(str(data.get("reason") or "").split())
    if not reason:
        raise ValidationError("Say why the statement isn't reliable.")
    review.statement_unreliable, review.unreliable_reason = True, reason
    db.session.commit()
    return review


def blockers(ex: Extraction, review: ExtractionReview) -> list[str]:
    out = []
    missing = _missing(ex, review)
    if missing:
        out.append(f"{missing} value(s) still need accept, correct or not present.")
    t = types.get(ex.declared_type)
    if t and t.statement and not review.statement_unreliable:
        bad = [p["page_number"] for p in page_checks(ex, review) if p["reviewed_status"] != PAGE_BALANCED]
        if bad:
            out.append(f"Page(s) {', '.join(map(str, sorted(bad)))} still don't add up: correct the rows, or mark "
                       "the statement not reliable.")
    return out


def submit(extraction_id: int, actor, application_id: int | None = None) -> ExtractionReview:
    review = _open(extraction_id, actor, application_id)
    _editable(review)
    ex = review_extraction(review)
    problems = blockers(ex, review)
    if problems:
        raise ValidationError(" ".join(problems))
    if application_id is not None:
        app = db.session.get(LoanApplication, application_id)
        if app is None:
            raise NotFound("Application not found.")
        review.application_id = app.id
    review.reviewed_by, review.submitted_at = actor.email, utcnow()
    cr = db.session.get(ChangeRequest, review.change_request_id) if review.change_request_id else None
    if cr is not None and cr.status == CR_RETURNED:
        db.session.flush()
        approvals.resubmit(cr.id, actor, {"review_id": review.id}, "Corrected and resubmitted.")
    else:
        cr = approvals.submit("ai.review", {"review_id": review.id}, actor, commit=False)
        review.change_request_id = cr.id
    create_audit_log("SUBMIT_AI_REVIEW", target_type="ai_extraction", target_id=ex.id, target_name=ex.declared_type,
                     description=f"Review of {types.label(ex.declared_type)} submitted for approval",
                     new_value=_snapshot(ex, review))
    db.session.commit()
    return review


def _snapshot(ex: Extraction, review: ExtractionReview) -> dict:
    corrections = {}
    fields = {f.id: f for f in ExtractedField.query.filter_by(extraction_id=ex.id)}
    for a in FieldReview.query.filter_by(review_id=review.id):
        if a.action != "accept":
            f = fields[a.field_id]
            corrections[f.field_path] = {"ai_value": f.value, "action": a.action, "value": a.corrected_value,
                                         "reason": a.reason}
    return {"review_id": review.id, "corrections": corrections,
            "rows_corrected": TransactionReview.query.filter_by(review_id=review.id).count(),
            "statement_unreliable": review.statement_unreliable}


# ── Approval: fill the client's blanks, compute confirmed metrics ──


def _write_party(ex: Extraction, values: dict) -> dict:
    party = parties.lock_party(ex.party_id)
    written, kept, refused = [], [], []
    for (doc_type, path), id_type in IDENTIFIER_FIELDS.items():
        value = values.get(path)
        if doc_type != ex.declared_type or not value:
            continue
        if (party.party_type == "organisation") != (id_type == "company_reg_no"):
            continue
        normalised = normalise_identifier(id_type, value)
        existing = PartyIdentifier.query.filter_by(party_id=party.id, id_type=id_type).first()
        label = ID_TYPE_LABELS[id_type]
        if existing is not None:
            if existing.value_normalised != normalised:
                kept.append(f"{label}: the record has {existing.value_display}, the document {value}")
            continue
        try:
            parties.assert_identifiers_free([{"id_type": id_type, "issuing_country": "KE",
                                              "value_normalised": normalised}], exclude_party_id=party.id)
        except Conflict as e:
            refused.append(e.message)
            continue
        db.session.add(PartyIdentifier(party_id=party.id, id_type=id_type, issuing_country="KE",
                                       value_display=value, value_normalised=normalised))
        written.append(f"{label} {value}")
    for (doc_type, path), (model, column) in DATE_FIELDS.items():
        when = validators.parse_iso_date(values.get(path))
        if doc_type != ex.declared_type or when is None:
            continue
        detail_row = db.session.get(model, party.id)
        if detail_row is None:
            continue
        current = getattr(detail_row, column)
        if current is None:
            setattr(detail_row, column, when)
            written.append(f"{column.replace('_', ' ')} {when.isoformat()}")
        elif current != when:
            kept.append(f"{column.replace('_', ' ')}: the record has {current.isoformat()}, the document "
                        f"{when.isoformat()}")
    if written:
        from app.Parties.changes import mirror_to_investor
        from app.Parties.screening import screen_party

        db.session.flush()
        mirror_to_investor(party)
        parties.refresh_kyc_status(party)
        screen_party(party, "identity_change", "ai-review")
        create_audit_log("UPDATE_PARTY_FROM_AI_REVIEW", target_type="party", target_id=party.id,
                         target_name=party.party_no, description="; ".join(written),
                         new_value={"written": written, "extraction_id": ex.id})
    return {"written": written, "kept_existing": kept, "refused": refused}


def confirmed_metrics(ex: Extraction, review: ExtractionReview) -> dict | None:
    t = types.get(ex.declared_type)
    if not (t and t.statement) or review.statement_unreliable:
        return None
    values = confirmed_values(ex, review)
    rows = reviewed_rows(ex, review)
    got, start, end = metrics.compute(rows, validators.parse_iso_date(values.get("header.period_from")),
                                      validators.parse_iso_date(values.get("header.period_to")),
                                      business.get("ai.statements.lender_keywords"),
                                      business.get("ai.statements.returned_item_keywords"))
    return {"period_from": start.isoformat() if start else None, "period_to": end.isoformat() if end else None,
            "metrics": {m.key: str(m.value) for m in got}}


@register
class AIReviewApproval(Handler):
    request_type = "ai.review"
    entity_type = "ai_extraction"
    submit_permission = "ai.review"

    def _review(self, payload) -> ExtractionReview:
        review_id = payload.get("review_id")
        review = db.session.get(ExtractionReview, review_id) if isinstance(review_id, int) else None
        if review is None:
            raise ValidationError("review_id must be a review.")
        return review

    def validate(self, payload):
        review = self._review(payload)
        if review.approved_at is not None:
            raise Conflict("This review is already approved.")
        problems = blockers(review_extraction(review), review)
        if problems:
            raise ValidationError(" ".join(problems))
        return {"review_id": review.id}

    def entity_id(self, payload):
        return str(self._review(payload).extraction_id)

    def branch_id(self, payload):
        party = db.session.get(Party, review_extraction(self._review(payload)).party_id)
        return party.home_branch_id if party else None

    def base_version(self, payload):
        review = self._review(payload)
        stamps = [r.reviewed_at.isoformat() for r in FieldReview.query.filter_by(review_id=review.id)]
        stamps += [r.reviewed_at.isoformat() for r in TransactionReview.query.filter_by(review_id=review.id)]
        return f"{len(stamps)}:{max(stamps) if stamps else ''}:{review.statement_unreliable}"

    def describe(self, payload):
        review = self._review(payload)
        ex = review_extraction(review)
        snap = _snapshot(ex, review)
        return (f"Approve the review of a {types.label(ex.declared_type)} (reading {ex.id}): "
                f"{len(snap['corrections'])} value(s) corrected or not present, {snap['rows_corrected']} row(s) "
                "corrected" + ("; statement marked not reliable" if review.statement_unreliable else ""))

    def old_value(self, payload):
        review = self._review(payload)
        return _snapshot(review_extraction(review), review)

    def apply(self, request, actor):
        review = db.session.query(ExtractionReview).filter_by(id=request.payload["review_id"]).with_for_update().one()
        ex = review_extraction(review)
        review.confirmed_metrics = confirmed_metrics(ex, review)
        review.party_updates = _write_party(ex, confirmed_values(ex, review))
        review.approved_by, review.approved_at = actor.email, utcnow()
        db.session.flush()
        return {"review_id": review.id, "party_updates": review.party_updates,
                "confirmed_metrics": review.confirmed_metrics}


def approved_review_for(extraction: Extraction) -> ExtractionReview | None:
    review = get_review(extraction.id)
    return review if is_approved(review) else None


def pending_change_request(review: ExtractionReview) -> bool:
    cr = db.session.get(ChangeRequest, review.change_request_id) if review.change_request_id else None
    return cr is not None and cr.status in CR_OPEN and cr.status != CR_APPLIED
