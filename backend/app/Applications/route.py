"""
Pre-screen applications (phase 3b).

    GET  /api/v1/applications                    list (?queue=ready_for_credit, ?search=)
    POST /api/v1/applications                    create (the instalment is an ESTIMATE)
    GET  /api/v1/applications/estimate           the estimate for a product, amount, term and rate
    GET  /api/v1/applications/<id>               detail, with documents and their readings
    POST /api/v1/applications/<id>/guarantors    {party_id}
    POST /api/v1/applications/<id>/documents     {document_id} of the applicant or a guarantor
    POST /api/v1/applications/<id>/crb           {status, status_date, bureau, extraction_id?}
"""
from flask import Blueprint, request

from app.Applications import service
from app.Applications.estimate import estimate
from app.Applications.model import PRODUCTS
from app.auth import current_user, requires
from app.utils.http import ValidationError, ok, page_args, paginate
from app.utils.money import as_str, parse_amount, parse_rate_percent

applications_v1 = Blueprint("applications_v1", __name__)


def _body() -> dict:
    return request.get_json(silent=True) or {}


@applications_v1.get("/api/v1/applications")
@requires("application.view")
def list_applications():
    page, per_page = page_args(request.args)
    a = request.args
    return ok(paginate(service.list_applications(queue=a.get("queue"), search=a.get("search")), page, per_page,
                       service.list_row))


@applications_v1.post("/api/v1/applications")
@requires("application.manage")
def create_application():
    row = service.create(_body(), current_user())
    return ok(service.summary(row), "Application created.", 201)


@applications_v1.get("/api/v1/applications/estimate")
@requires("application.manage")
def instalment_estimate():
    a = request.args
    product = a.get("product_code") or ""
    if product not in PRODUCTS:
        raise ValidationError(f"product_code must be one of: {', '.join(PRODUCTS)}.")
    amount = parse_amount(a.get("amount_requested"), "amount_requested")
    rate = parse_rate_percent(a.get("indicative_rate_percent"), "indicative_rate_percent")
    term = service._term(a.get("term_months"), product)
    instalment, final = estimate(product, amount, term, rate)
    return ok({"estimated_instalment": as_str(instalment), "estimated_final_payment": as_str(final),
               "repayment": PRODUCTS[product][3],
               "estimate_note": "Estimate only: phase 5's product engine will calculate the actual schedule."})


@applications_v1.get("/api/v1/applications/<int:application_id>")
@requires("application.view")
def application_detail(application_id):
    return ok(service.detail(application_id))


@applications_v1.post("/api/v1/applications/<int:application_id>/guarantors")
@requires("application.manage")
def add_guarantor(application_id):
    try:
        party_id = int(_body().get("party_id"))
    except (TypeError, ValueError):
        raise ValidationError("party_id is required.")
    service.add_guarantor(application_id, party_id, current_user())
    return ok(service.summary(service.get(application_id)), "Guarantor added.", 201)


@applications_v1.post("/api/v1/applications/<int:application_id>/documents")
@requires("application.manage")
def link_document(application_id):
    service.link_document(application_id, _body().get("document_id"), current_user())
    return ok({"document_id": _body().get("document_id")}, "Document added to the application.", 201)


@applications_v1.post("/api/v1/applications/<int:application_id>/crb")
@requires("application.manage")
def enter_crb(application_id):
    row = service.enter_crb(application_id, _body(), current_user())
    return ok(row.to_dict(), "CRB status entered; a second person must confirm it.", 201)


# ── Review of an AI reading (AI-07): maker here, checker in the approvals inbox ──


@applications_v1.get("/api/v1/extractions/<int:extraction_id>/review")
@requires("ai.extract.view")
def review_detail(extraction_id):
    from app.Applications import review
    return ok(review.detail(extraction_id, current_user()))


@applications_v1.post("/api/v1/extractions/<int:extraction_id>/review/fields/<int:field_id>")
@requires("ai.review")
def review_field(extraction_id, field_id):
    from app.Applications import review
    review.set_field(extraction_id, field_id, _body(), current_user(), _application_id())
    return ok(review.detail(extraction_id, current_user()), "Saved.")


@applications_v1.post("/api/v1/extractions/<int:extraction_id>/review/transactions/<int:transaction_id>")
@requires("ai.review")
def review_transaction(extraction_id, transaction_id):
    from app.Applications import review
    review.set_transaction(extraction_id, transaction_id, _body(), current_user(), _application_id())
    return ok(review.detail(extraction_id, current_user()), "Row corrected.")


@applications_v1.post("/api/v1/extractions/<int:extraction_id>/review/unreliable")
@requires("ai.review")
def review_unreliable(extraction_id):
    from app.Applications import review
    review.mark_unreliable(extraction_id, _body(), current_user(), _application_id())
    return ok(review.detail(extraction_id, current_user()), "Statement marked not reliable.")


@applications_v1.post("/api/v1/extractions/<int:extraction_id>/review/submit")
@requires("ai.review")
def review_submit(extraction_id):
    from app.Applications import review
    row = review.submit(extraction_id, current_user(), _application_id())
    return ok({"review_id": row.id, "change_request_id": row.change_request_id},
              "Submitted: a different person must approve before anything is saved to the client.", 201)


def _application_id() -> int | None:
    value = _body().get("application_id")
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValidationError("application_id must be an application id.")


@applications_v1.get("/api/v1/applications/<int:application_id>/checks")
@requires("application.view")
def application_checks(application_id):
    from app.Applications import checks
    return ok(checks.run(application_id))


# ── Pre-selection and decision (AI-08, AI-09) ──


@applications_v1.post("/api/v1/applications/<int:application_id>/screen")
@requires("application.manage")
def screen_application(application_id):
    from app.Applications import screening
    run = screening.screen(application_id, current_user())
    return ok(screening.run_dict(run), f"Recommendation: {screening.OUTCOME_LABELS[run.outcome]}.", 201)


@applications_v1.get("/api/v1/applications/<int:application_id>/runs")
@requires("application.view")
def application_runs(application_id):
    from app.Applications import screening
    from app.Applications.model import ScreeningRun
    service.get(application_id)
    runs = (ScreeningRun.query.filter_by(application_id=application_id)
            .order_by(ScreeningRun.evaluated_at.desc(), ScreeningRun.id.desc()).all())
    return ok([screening.run_dict(r) for r in runs])


@applications_v1.post("/api/v1/applications/<int:application_id>/decision")
@requires("credit.decide")
def record_decision(application_id):
    from app.Applications import screening
    result = screening.decide(application_id, _body(), current_user())
    if result["status"] == "pending_approval":
        return ok(result, "Proceeding against a Not qualified recommendation needs a second approver.", 202)
    return ok(result, "Decision recorded.", 201)


@applications_v1.get("/api/v1/screening/rule-set")
@requires("application.view")
def rule_set():
    from app.Applications.ruleset import COMPARISONS, FAIL_OUTCOMES, METRICS, PRODUCT_CODES, PROTECTED
    from app.Settings import business
    row = business.current_version("screening.rule_set")
    return ok({"version_id": row.id if row else None, "version_no": row.version_no if row else None,
               "effective_from": row.effective_from.isoformat() if row else None,
               "rule_set": row.value if row else None,
               "metrics": [{"name": k, "kind": v[0], "description": v[1]} for k, v in METRICS.items()],
               "comparisons": list(COMPARISONS), "outcomes": list(FAIL_OUTCOMES), "products": list(PRODUCT_CODES),
               "protected_attributes": sorted(PROTECTED)})


# ── Oversight (AI-10, AI-12, AI-13) ──


@applications_v1.get("/api/v1/applications/<int:application_id>/log")
@requires("application.view", "ai.extract.view")
def decision_log(application_id):
    from app.Applications import reports
    return ok(reports.decision_log(application_id, current_user()))


@applications_v1.get("/api/v1/ai/usage")
@requires("ai.extract.view")
def ai_usage():
    from app.Applications import reports
    try:
        months = int(request.args.get("months") or 12)
    except ValueError:
        raise ValidationError("months must be a whole number.")
    return ok(reports.usage(months))


@applications_v1.get("/api/v1/ai/accuracy")
@requires("ai.extract.view")
def ai_accuracy():
    from app.Applications import reports
    return ok(reports.accuracy())


@applications_v1.get("/api/v1/ai/status")
@requires("ai.extract.view")
def ai_status():
    from app.DocAI import guard
    return ok(guard.status())


@applications_v1.post("/api/v1/ai/resume")
@requires("ai.breaker.resume")
def ai_resume():
    from app.DocAI import guard
    row = guard.resume(current_user(), _body().get("reason"))
    return ok(row.to_dict(), "AI document reading resumed.")
