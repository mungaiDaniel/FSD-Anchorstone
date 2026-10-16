"""
Clients (parties).

    GET   /api/v1/parties                         ?search ?type ?kyc_status ?role
    POST  /api/v1/parties                         individual or organisation
    GET   /api/v1/parties/<id>
    PATCH /api/v1/parties/<id>                    direct fields save; identity/bank/payout → party.change
    POST  /api/v1/parties/<id>/relationships      next of kin, director, guarantor …
    POST  /api/v1/parties/<id>/relationships/<rid>/end
    PUT   /api/v1/parties/<id>/mandate            signing rule
    POST  /api/v1/parties/<id>/verify             submits a party.verify change request
    POST  /api/v1/parties/<id>/investor           opens an investment account (investor role)
    POST  /api/v1/parties/check-duplicates        identifiers that would be refused, phones/emails in use
    PUT   /api/v1/parties/<id>/pep                PEP flag and details (party.pep_approve, 2 approvers)
    GET   /api/v1/parties/<id>/screening          screening history
    GET   /api/v1/screening-results               the review queue (?review_status=pending|cleared|…|all)
    POST  /api/v1/screening-results/<id>/review   {decision: clear|confirmed, note}
    GET   /api/v1/watchlist   POST /api/v1/watchlist   POST /api/v1/watchlist/<id>/remove (change request)
    GET   /api/v1/parties/<id>/documents          current and earlier versions, by type
    POST  /api/v1/parties/<id>/documents          multipart: file, document_type (FSD 5.1 list)
    GET   /api/v1/parties/<id>/consents   POST …/consents   POST …/consents/<cid>/withdraw
"""
from flask import Blueprint, request

from app.Approvals import service as approvals
from app.auth import actor_email, current_user, requires
from app.Parties import consent, documents, screening, service
from app.Parties.model import ScreeningResult, WatchlistEntry
from app.utils.http import ValidationError, ok, page_args, paginate

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
    body = _body()
    party = service.create_party(body, actor_email())
    if isinstance(body.get("pep"), dict) and body["pep"].get("is_pep") is True:
        service.set_pep(party.id, body["pep"], current_user())
    warnings = getattr(party, "warnings", [])
    message = f"Client {party.party_no} created." + (" Check the duplicate warnings." if warnings else "")
    return ok({**service.party_detail(party), "warnings": warnings}, message, 201)


@parties_v1.get("/api/v1/parties/<int:party_id>")
@requires("party.view")
def get_party(party_id):
    return ok(service.party_detail(service.get_party(party_id)))


@parties_v1.patch("/api/v1/parties/<int:party_id>")
@requires("party.edit")
def edit_party(party_id):
    """Contact and other details save at once; identity, bank and payout changes go for approval (KYC-08)."""
    from app.Parties.changes import describe_groups, edit_party as edit

    result = edit(party_id, _body(), current_user())
    cr = result["change_request"]
    parts = []
    if result["saved"]:
        parts.append("Saved.")
    if cr is not None:
        parts.append(f"The {describe_groups(cr.payload['changes']['groups'])} change needs a second person's "
                     f"approval (request #{cr.id}).")
    return ok({**service.party_detail(service.get_party(party_id)), "saved": result["saved"],
               "change_request": cr.to_dict(approvals.summary(cr)) if cr else None},
              " ".join(parts) or "Nothing changed.")


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


# ── Duplicates, screening and PEP (KYC-05, 06, 07) ──


@parties_v1.post("/api/v1/parties/check-duplicates")
@requires("party.create")
def check_duplicates():
    """{identifiers, contacts, exclude_party_id?}: conflicts (would be refused) and warnings (phone, email)."""
    body = _body()
    exclude = body.get("exclude_party_id") if isinstance(body.get("exclude_party_id"), int) else None
    return ok(service.check_duplicates(body, exclude))


@parties_v1.put("/api/v1/parties/<int:party_id>/pep")
@requires("party.edit")
def set_pep(party_id):
    cr = service.set_pep(party_id, _body(), current_user())
    return ok(cr.to_dict(approvals.summary(cr)), "PEP details saved. Two senior approvers must approve them.", 201)


@parties_v1.get("/api/v1/parties/<int:party_id>/screening")
@requires("party.view")
def party_screening(party_id):
    service.get_party(party_id)
    rows = ScreeningResult.query.filter_by(party_id=party_id).order_by(ScreeningResult.screened_at.desc(),
                                                                      ScreeningResult.id.desc()).all()
    return ok([r.to_dict() for r in rows])


@parties_v1.get("/api/v1/screening-results")
@requires("screening.review")
def screening_queue():
    page, per_page = page_args(request.args)
    q = ScreeningResult.query
    status = request.args.get("review_status") or "pending"
    if status != "all":
        q = q.filter(ScreeningResult.review_status == status)
    q = q.order_by(ScreeningResult.screened_at.desc(), ScreeningResult.id.desc())

    def out(r):
        return {**r.to_dict(), "party": service.get_party(r.party_id).summary()}
    return ok(paginate(q, page, per_page, out))


@parties_v1.post("/api/v1/screening-results/<int:result_id>/review")
@requires("screening.review")
def review_screening(result_id):
    row = screening.review(result_id, _body(), actor_email())
    return ok(row.to_dict(), f"Match {row.review_status}.")


@parties_v1.get("/api/v1/watchlist")
@requires("watchlist.manage")
def list_watchlist():
    page, per_page = page_args(request.args)
    q = WatchlistEntry.query
    if request.args.get("list"):
        q = q.filter(WatchlistEntry.list == request.args["list"])
    if request.args.get("status") != "all":
        q = q.filter(WatchlistEntry.status == "active")
    if request.args.get("search"):
        q = q.filter(WatchlistEntry.full_name.ilike(f"%{request.args['search'].strip()}%"))
    return ok(paginate(q.order_by(WatchlistEntry.full_name), page, per_page, lambda e: e.to_dict()))


@parties_v1.post("/api/v1/watchlist")
@requires("watchlist.manage")
def add_watchlist_entry():
    entry, found = screening.add_entry(_body(), actor_email())
    message = "Added to the watchlist." + (f" {found} client(s) match and need review." if found else "")
    return ok({**entry.to_dict(), "matched_parties": found}, message, 201)


@parties_v1.post("/api/v1/watchlist/<int:entry_id>/remove")
@requires("watchlist.manage")
def remove_watchlist_entry(entry_id):
    cr = approvals.submit("watchlist.remove", {"entry_id": entry_id, "reason": _body().get("reason")}, current_user())
    return ok(cr.to_dict(approvals.summary(cr)), "Removal submitted for approval.", 201)


# ── Documents and consent ──


@parties_v1.get("/api/v1/parties/<int:party_id>/documents")
@requires("party.view", "document.view")
def party_documents(party_id):
    service.get_party(party_id)
    return ok(documents.for_party(party_id))


@parties_v1.post("/api/v1/parties/<int:party_id>/documents")
@requires("document.upload")
def upload_party_document(party_id):
    file = request.files.get("file")
    if file is None:
        raise ValidationError("Attach the file as 'file'.")
    doc = documents.upload_for_party(party_id, file.read(), filename=file.filename, content_type=file.mimetype,
                                     document_type=request.form.get("document_type") or "", actor=current_user())
    return ok(doc.to_dict(), "Document uploaded.", 201)


@parties_v1.get("/api/v1/parties/<int:party_id>/consents")
@requires("party.view")
def party_consents(party_id):
    service.get_party(party_id)
    return ok([c.to_dict() for c in consent.for_party(party_id)])


@parties_v1.post("/api/v1/parties/<int:party_id>/consents")
@requires("consent.capture")
def record_consent(party_id):
    return ok(consent.record(party_id, _body(), actor_email()).to_dict(), "Consent recorded.", 201)


@parties_v1.post("/api/v1/parties/<int:party_id>/consents/<int:consent_id>/withdraw")
@requires("consent.capture")
def withdraw_consent(party_id, consent_id):
    return ok(consent.withdraw(party_id, consent_id, _body(), actor_email()).to_dict(), "Consent withdrawn.")
