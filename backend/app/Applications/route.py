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
