"""
Oversight of AI extraction and pre-selection (AI-10, AI-12, AI-13).

    usage(months)                   AI calls, tokens and estimated cost per Nairobi month, document
                                    type and model (from ai_extraction_calls)
    accuracy()                      per document type: values accepted as read, corrected, or not
                                    present in approved reviews, and corrections made to values the
                                    AI was confident about (evidence for the accuracy sign-off)
    decision_log(application_id)    everything behind one recommendation and decision: documents,
                                    readings (model, prompt and schema versions, cost), reviews with
                                    each correction beside the AI value, confirmed metrics, checks,
                                    every rule result with its reason, CRB status, decisions
"""
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import func, text

from app.Applications import checks as cross_checks
from app.Applications import review as reviews
from app.Applications import screening
from app.Applications import service as applications
from app.Applications.model import (
    ApplicationCrbStatus,
    ExtractionReview,
    FieldReview,
    ScreeningRun,
    TransactionReview,
)
from app.database.database import db
from app.DocAI import types
from app.DocAI.model import ExtractedField, Extraction, ExtractionCall, StatementTransaction
from app.Documents.model import DataAccessLog
from app.utils.audit_log import AuditLog, get_client_ip
from app.utils.dates import iso, utcnow
from app.utils.money import as_str


def usage(months: int = 12) -> dict:
    rows = db.session.execute(text("""
        SELECT to_char((c.started_at AT TIME ZONE 'UTC') + interval '3 hours', 'YYYY-MM') AS month,
               e.declared_type AS doc_type, COALESCE(c.model_returned, c.model_requested) AS model,
               count(*) AS calls, count(*) FILTER (WHERE c.outcome = 'ok') AS ok_calls,
               count(DISTINCT c.extraction_id) AS readings,
               COALESCE(sum(c.input_tokens), 0) AS input_tokens, COALESCE(sum(c.output_tokens), 0) AS output_tokens,
               COALESCE(sum(c.cost_usd), 0) AS cost_usd
        FROM ai_extraction_calls c JOIN ai_extractions e ON e.id = c.extraction_id
        GROUP BY 1, 2, 3 ORDER BY 1 DESC, 2, 3""")).mappings().all()
    keep = sorted({r["month"] for r in rows}, reverse=True)[:max(1, min(months, 60))]
    out = {}
    for r in rows:
        if r["month"] not in keep:
            continue
        month = out.setdefault(r["month"], {"month": r["month"], "calls": 0, "readings": 0, "input_tokens": 0,
                                            "output_tokens": 0, "cost_usd": Decimal("0"), "by_type": []})
        cost = Decimal(r["cost_usd"])
        month["by_type"].append({"document_type": r["doc_type"], "label": types.label(r["doc_type"]),
                                 "model": r["model"], "calls": r["calls"], "ok_calls": r["ok_calls"],
                                 "readings": r["readings"], "input_tokens": int(r["input_tokens"]),
                                 "output_tokens": int(r["output_tokens"]), "cost_usd": f"{cost:.6f}",
                                 "cost_per_reading_usd": f"{cost / r['readings']:.6f}" if r["readings"] else None})
        for k in ("calls", "readings", "input_tokens", "output_tokens"):
            month[k] += int(r[k])
        month["cost_usd"] += cost
    for month in out.values():
        month["cost_usd"] = f"{month['cost_usd']:.6f}"
        month["refusals"] = []
    from app.DocAI.model import AIBudgetRefusal
    for refusal in AIBudgetRefusal.query.order_by(AIBudgetRefusal.refused_at.desc(), AIBudgetRefusal.id.desc()):
        label = (refusal.refused_at + timedelta(hours=3)).strftime("%Y-%m")
        if label in keep and label in out:
            out[label]["refusals"].append(refusal.to_dict())
        elif label not in out and len(out) < max(1, min(months, 60)):
            out[label] = {"month": label, "calls": 0, "readings": 0, "input_tokens": 0, "output_tokens": 0,
                          "cost_usd": "0.000000", "by_type": [], "refusals": [refusal.to_dict()]}
            keep = sorted(set(keep) | {label}, reverse=True)
    return {"months": [out[m] for m in keep if m in out], "currency": "USD",
            "note": "Estimated from tokens × ai.price_table at the time of each call."}


def accuracy() -> list[dict]:
    limit = reviews.threshold()
    q = (db.session.query(Extraction.declared_type, FieldReview.action, ExtractedField.confidence)
         .join(ExtractedField, ExtractedField.id == FieldReview.field_id)
         .join(ExtractionReview, ExtractionReview.id == FieldReview.review_id)
         .join(Extraction, Extraction.id == ExtractionReview.extraction_id)
         .filter(ExtractionReview.approved_at.isnot(None)))
    stats: dict[str, dict] = {}
    for doc_type, action, confidence in q:
        s = stats.setdefault(doc_type, {"document_type": doc_type, "label": types.label(doc_type), "values": 0,
                                        "accepted": 0, "corrected": 0, "not_present": 0,
                                        "confident_but_corrected": 0})
        s["values"] += 1
        s["accepted" if action == "accept" else "corrected" if action == "correct" else "not_present"] += 1
        if action == "correct" and confidence is not None and confidence >= limit:
            s["confident_but_corrected"] += 1
    rows_corrected = dict(db.session.query(Extraction.declared_type, func.count(TransactionReview.id))
                          .join(ExtractionReview, ExtractionReview.id == TransactionReview.review_id)
                          .join(Extraction, Extraction.id == ExtractionReview.extraction_id)
                          .filter(ExtractionReview.approved_at.isnot(None)).group_by(Extraction.declared_type).all())
    out = []
    for s in sorted(stats.values(), key=lambda x: x["document_type"]):
        read = s["accepted"] + s["corrected"]
        s["accepted_as_read_percent"] = f"{Decimal(s['accepted']) * 100 / read:.1f}" if read else None
        s["statement_rows_corrected"] = rows_corrected.get(s["document_type"], 0)
        out.append(s)
    return out


def _corrections(ex: Extraction, review: ExtractionReview) -> tuple[list[dict], list[dict]]:
    fields = {f.id: f for f in ExtractedField.query.filter_by(extraction_id=ex.id)}
    out = []
    for a in FieldReview.query.filter_by(review_id=review.id).order_by(FieldReview.id):
        f = fields[a.field_id]
        out.append({"field": f.field_path, "ai_value": f.value,
                    "ai_confidence": None if f.confidence is None else str(f.confidence), "page": f.source_page,
                    "action": a.action, "confirmed_value": f.value if a.action == "accept" else a.corrected_value,
                    "reason": a.reason, "reviewed_by": a.reviewed_by, "reviewed_at": iso(a.reviewed_at)})
    rows = []
    for t in TransactionReview.query.filter_by(review_id=review.id).order_by(TransactionReview.id):
        ai = db.session.get(StatementTransaction, t.transaction_id)
        rows.append({"page": ai.page_number, "row": ai.row_no, "description": ai.description,
                     "ai": {"date": iso(ai.txn_date), "debit": as_str(ai.debit), "credit": as_str(ai.credit),
                            "balance": as_str(ai.balance)},
                     "confirmed": {"date": iso(t.txn_date), "debit": as_str(t.debit), "credit": as_str(t.credit),
                                   "balance": as_str(t.balance)}, "reason": t.reason, "reviewed_by": t.reviewed_by})
    return out, rows


def decision_log(application_id: int, actor) -> dict:
    app = applications.get(application_id)
    docs = applications.documents(app.id)
    readings = []
    for doc in docs:
        for ex in (Extraction.query.filter_by(document_id=doc["id"])
                   .order_by(Extraction.requested_at, Extraction.id)):
            review = reviews.get_review(ex.id)
            fields, rows = _corrections(ex, review) if review else ([], [])
            readings.append({
                "document_id": doc["id"], "extraction": ex.to_dict(), "label": types.label(ex.declared_type),
                "calls": ExtractionCall.query.filter_by(extraction_id=ex.id).count(),
                "review": None if review is None else {
                    "state": reviews.state(review), "reviewed_by": review.reviewed_by,
                    "submitted_at": iso(review.submitted_at), "approved_by": review.approved_by,
                    "approved_at": iso(review.approved_at), "change_request_id": review.change_request_id,
                    "statement_unreliable": review.statement_unreliable,
                    "unreliable_reason": review.unreliable_reason, "values": fields, "rows_corrected": rows,
                    "confirmed_metrics": review.confirmed_metrics, "party_updates": review.party_updates}})
            db.session.add(DataAccessLog(user_id=actor.id, user_email=actor.email, document_id=ex.document_id,
                                         entity_type="ai_extraction", entity_id=str(ex.id), action="view",
                                         ip_address=get_client_ip(), at=utcnow()))
    runs = (ScreeningRun.query.filter_by(application_id=app.id)
            .order_by(ScreeningRun.evaluated_at, ScreeningRun.id).all())
    crb = (ApplicationCrbStatus.query.filter_by(application_id=app.id)
           .order_by(ApplicationCrbStatus.entered_at, ApplicationCrbStatus.id).all())
    trail = (AuditLog.query.filter(AuditLog.target_type == "loan_application",
                                   AuditLog.target_id == app.id).order_by(AuditLog.id).all())
    db.session.commit()
    return {"application": applications.summary(app), "documents": docs, "readings": readings,
            "crb_statuses": [c.to_dict() for c in crb], "checks": cross_checks.run(app.id),
            "runs": [screening.run_dict(r) for r in runs], "decisions": screening.decisions(app.id),
            "audit": [{"action": a.action, "description": a.description, "user": a.user_email,
                       "at": iso(a.timestamp)} for a in trail]}
