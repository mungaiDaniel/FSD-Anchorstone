"""
Clients (parties).

    GET   /api/v1/parties                         ?search ?type ?kyc_status ?role
    POST  /api/v1/parties                         individual or organisation
    GET   /api/v1/parties/<id>
    POST  /api/v1/parties/<id>/relationships      next of kin, director, guarantor …
    POST  /api/v1/parties/<id>/relationships/<rid>/end
    PUT   /api/v1/parties/<id>/mandate            signing rule
    POST  /api/v1/parties/<id>/verify             submits a party.verify change request
    POST  /api/v1/parties/<id>/investor           opens an investment account (investor role)
"""
from flask import Blueprint, request

from app.Approvals import service as approvals
from app.auth import actor_email, current_user, requires
from app.Parties import service
from app.utils.http import ok, page_args

parties_v1 = Blueprint("parties_v1", __name__)


def _body() -> dict:
    return request.get_json(silent=True) or {}


@parties_v1.get("/api/v1/parties")
@requires("party.view")
def list_parties():
    page, per_page = page_args(request.args)
    a = request.args
    return ok(service.list_parties(a.get("search"), a.get("type"), a.get("kyc_status"), a.get("role"), page, per_page))


@parties_v1.post("/api/v1/parties")
@requires("party.create")
def create_party():
    party = service.create_party(_body(), actor_email())
    return ok(service.party_detail(party), f"Client {party.party_no} created.", 201)


@parties_v1.get("/api/v1/parties/<int:party_id>")
@requires("party.view")
def get_party(party_id):
    return ok(service.party_detail(service.get_party(party_id)))


@parties_v1.post("/api/v1/parties/<int:party_id>/relationships")
@requires("party.edit")
def add_relationship(party_id):
    row = service.add_relationship(party_id, _body(), actor_email())
    return ok(row.to_dict(), "Related party added.", 201)


@parties_v1.post("/api/v1/parties/<int:party_id>/relationships/<int:relationship_id>/end")
@requires("party.edit")
def end_relationship(party_id, relationship_id):
    return ok(service.end_relationship(party_id, relationship_id, actor_email()).to_dict(), "Relationship ended.")


@parties_v1.put("/api/v1/parties/<int:party_id>/mandate")
@requires("party.edit")
def set_mandate(party_id):
    return ok(service.set_mandate(party_id, _body(), actor_email()).to_dict(), "Signing rule saved.")


@parties_v1.post("/api/v1/parties/<int:party_id>/verify")
@requires("party.edit")
def request_verification(party_id):
    cr = service.request_verification(party_id, current_user(), _body().get("reason"))
    return ok(cr.to_dict(approvals.summary(cr)), "Submitted for KYC verification.", 201)


@parties_v1.post("/api/v1/parties/<int:party_id>/investor")
@requires("investor.create")
def attach_investor(party_id):
    """Open an investment account for an existing client (the next ACL- code); body {email?, notes?}."""
    from app.Investors import service as investors

    investor = investors.attach_investor(party_id, _body(), actor_email())
    return ok(investors.investor_summary(investor), f"Investor {investor.client_code} created.", 201)
