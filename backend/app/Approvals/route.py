"""
Change requests (the Approvals inbox API).

    GET  /api/v1/change-requests                 requests I may decide now
         ?mine=1                                 requests I made
         ?status=<status>                        every request in that status
    GET  /api/v1/change-requests/<id>            one request with its events
    POST /api/v1/change-requests                 {request_type, payload, reason}
    POST /api/v1/change-requests/<id>/approve    {comment}
    POST /api/v1/change-requests/<id>/reject     {reason}
    POST /api/v1/change-requests/<id>/return     {reason}
    POST /api/v1/change-requests/<id>/resubmit   {payload, reason}   (maker)
    POST /api/v1/change-requests/<id>/cancel                         (maker)

Submitting needs the handler's own permission; deciding needs the current
level's permission and limit (checked in the service, not the route).
"""
from flask import Blueprint, request

from app.Approvals import service
from app.Approvals.model import CR_STATUSES, ChangeRequest
from app.auth import current_user, requires
from app.database.database import db
from app.utils.http import NotFound, ValidationError, ok, page_args, paginate

approvals_v1 = Blueprint("approvals_v1", __name__)


def _body() -> dict:
    return request.get_json(silent=True) or {}


def _out(cr: ChangeRequest, with_events: bool = False) -> dict:
    data = cr.to_dict(service.summary(cr))
    data["can_decide"] = service.can_decide(cr, current_user())
    if with_events:
        data["events"] = [e.to_dict() for e in service.events(cr)]
    return data


@approvals_v1.get("/api/v1/change-requests")
@requires("change_request.view")
def list_change_requests():
    page, per_page = page_args(request.args)
    status = request.args.get("status")
    if status and status not in CR_STATUSES:
        raise ValidationError(f"status must be one of: {', '.join(CR_STATUSES)}.")
    result = service.inbox(current_user(), status=status, mine=request.args.get("mine") in ("1", "true"))
    if isinstance(result, list):
        items = result[(page - 1) * per_page: page * per_page]
        return ok({"items": [_out(cr) for cr in items], "total": len(result), "page": page, "per_page": per_page})
    return ok(paginate(result, page, per_page, _out))


@approvals_v1.get("/api/v1/change-requests/<int:request_id>")
@requires("change_request.view")
def get_change_request(request_id):
    cr = db.session.get(ChangeRequest, request_id)
    if cr is None:
        raise NotFound("Change request not found.")
    return ok(_out(cr, with_events=True))


@approvals_v1.post("/api/v1/change-requests")
@requires("change_request.view")
def submit_change_request():
    data = _body()
    cr = service.submit(data.get("request_type") or "", data.get("payload"), current_user(), data.get("reason"))
    return ok(_out(cr), "Submitted for approval.", 201)


@approvals_v1.post("/api/v1/change-requests/<int:request_id>/approve")
@requires("change_request.view")
def approve_change_request(request_id):
    cr = service.approve(request_id, current_user(), _body().get("comment"))
    return ok(_out(cr), "Approved and applied." if cr.status == "applied" else "Approved. It needs another approval.")


@approvals_v1.post("/api/v1/change-requests/<int:request_id>/reject")
@requires("change_request.view")
def reject_change_request(request_id):
    return ok(_out(service.reject(request_id, current_user(), _body().get("reason"))), "Rejected.")


@approvals_v1.post("/api/v1/change-requests/<int:request_id>/return")
@requires("change_request.view")
def return_change_request(request_id):
    cr = service.return_for_correction(request_id, current_user(), _body().get("reason"))
    return ok(_out(cr), "Returned to the maker for correction.")


@approvals_v1.post("/api/v1/change-requests/<int:request_id>/resubmit")
@requires("change_request.view")
def resubmit_change_request(request_id):
    data = _body()
    cr = service.resubmit(request_id, current_user(), data.get("payload"), data.get("reason"))
    return ok(_out(cr), "Resubmitted for approval.")


@approvals_v1.post("/api/v1/change-requests/<int:request_id>/cancel")
@requires("change_request.view")
def cancel_change_request(request_id):
    return ok(_out(service.cancel(request_id, current_user())), "Cancelled.")
