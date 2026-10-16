"""
Party change requests (maker-checker through app/Approvals).

    party.verify        mark a client's KYC verified; refused while compulsory
                        details are missing, a screening match is unreviewed or
                        PEP details await approval. Approved by kyc.verify.
    party.pep_approve   PEP details (or clearing the flag), two kyc.pep.approve
                        approvers by policy (KYC-07)
    watchlist.remove    take a name off a watchlist
"""
import hashlib
import json

from app.Approvals.handlers import Handler, register
from app.Parties import service
from app.Parties.model import Party, PartyPepDetails, WatchlistEntry
from app.database.database import db
from app.utils.audit_log import create_audit_log
from app.utils.dates import utcnow
from app.utils.http import Conflict, ValidationError


def _party_id(payload) -> int:
    party_id = payload.get("party_id")
    if not isinstance(party_id, int) or isinstance(party_id, bool):
        raise ValidationError("party_id is required.")
    return party_id


class _PartyHandler(Handler):
    entity_type = "party"

    def entity_id(self, payload):
        return str(payload["party_id"])

    def branch_id(self, payload):
        party = db.session.get(Party, payload["party_id"])
        return party.home_branch_id if party else None


@register
class VerifyParty(_PartyHandler):
    request_type = "party.verify"
    submit_permission = "party.edit"

    def validate(self, payload):
        party = service.get_party(_party_id(payload))
        if party.kyc_status == "verified":
            raise Conflict(f"{party.party_no} is already verified.")
        blockers = service.verification_blockers(party)
        if blockers:
            raise ValidationError(" ".join(blockers))
        return {"party_id": party.id}

    def base_version(self, payload):
        party = db.session.get(Party, payload["party_id"])
        return f"{party.kyc_status}:{party.status}" if party else None

    def describe(self, payload):
        party = db.session.get(Party, payload["party_id"])
        return f"Verify KYC for {party.party_no} {party.display_name}" if party else "Verify KYC"

    def old_value(self, payload):
        party = db.session.get(Party, payload["party_id"])
        return {"kyc_status": party.kyc_status} if party else None

    def apply(self, request, actor):
        party = service.lock_party(request.payload["party_id"])
        old = party.kyc_status
        party.kyc_status, party.verified_at, party.verified_by = "verified", utcnow(), actor.email
        create_audit_log("VERIFY_PARTY_KYC", target_type="party", target_id=party.id, target_name=party.party_no,
                         old_value={"kyc_status": old},
                         new_value={"kyc_status": "verified", "change_request_id": request.id})
        return {"party_no": party.party_no, "kyc_status": party.kyc_status}


@register
class ApprovePep(_PartyHandler):
    """KYC-07: senior approval (two approvers by policy) of a PEP flag and its details, or of clearing it."""
    request_type = "party.pep_approve"
    submit_permission = "party.edit"

    def validate(self, payload):
        party = service.get_party(_party_id(payload))
        action = payload.get("action")
        if action not in ("approve", "clear"):
            raise ValidationError("action must be approve or clear.")
        if not party.is_pep:
            raise Conflict(f"{party.party_no} isn't flagged as a PEP.")
        pep = db.session.get(PartyPepDetails, party.id)
        if action == "approve" and (pep is None or pep.status != "pending"):
            raise Conflict("There are no PEP details waiting for approval.")
        return {"party_id": party.id, "action": action}

    def base_version(self, payload):
        party = db.session.get(Party, payload["party_id"])
        pep = db.session.get(PartyPepDetails, payload["party_id"])
        details = json.dumps(pep.to_dict(), sort_keys=True) if pep else "-"
        return hashlib.sha256(f"{party.is_pep}:{details}".encode()).hexdigest()

    def describe(self, payload):
        party = db.session.get(Party, payload["party_id"])
        name = f"{party.party_no} {party.display_name}" if party else str(payload["party_id"])
        return f"Approve PEP details for {name}" if payload["action"] == "approve" else f"Clear the PEP flag on {name}"

    def old_value(self, payload):
        pep = db.session.get(PartyPepDetails, payload["party_id"])
        return pep.to_dict() if pep else None

    def apply(self, request, actor):
        from app.Approvals.model import ChangeRequestEvent

        party = service.lock_party(request.payload["party_id"])
        pep = db.session.get(PartyPepDetails, party.id)
        approvers = [e.actor_email for e in ChangeRequestEvent.query.filter_by(
            request_id=request.id, round=request.round, action="approve").order_by(ChangeRequestEvent.id)]
        if request.payload["action"] == "approve":
            pep.status, pep.approved_at, pep.approved_by = "approved", utcnow(), ", ".join(approvers)[:250]
        else:
            party.is_pep = False
            if pep is not None:
                pep.status, pep.approved_at, pep.approved_by = "cleared", None, None
        create_audit_log("APPROVE_PARTY_PEP" if request.payload["action"] == "approve" else "CLEAR_PARTY_PEP",
                         target_type="party", target_id=party.id, target_name=party.party_no,
                         new_value={"is_pep": party.is_pep, "pep_status": pep.status if pep else None,
                                    "approved_by": approvers, "change_request_id": request.id})
        return {"party_no": party.party_no, "is_pep": party.is_pep}


@register
class RemoveWatchlistEntry(Handler):
    request_type = "watchlist.remove"
    entity_type = "watchlist_entry"
    submit_permission = "watchlist.manage"

    def validate(self, payload):
        entry = db.session.get(WatchlistEntry, payload.get("entry_id") if isinstance(payload.get("entry_id"), int) else -1)
        if entry is None:
            raise ValidationError("entry_id must be a watchlist entry.")
        if entry.status != "active":
            raise Conflict("This entry has already been removed.")
        reason = str(payload.get("reason") or "").strip()
        if not reason:
            raise ValidationError("A reason is required.")
        return {"entry_id": entry.id, "reason": reason[:2000]}

    def entity_id(self, payload):
        return str(payload["entry_id"])

    def base_version(self, payload):
        entry = db.session.get(WatchlistEntry, payload["entry_id"])
        return entry.status if entry else None

    def describe(self, payload):
        entry = db.session.get(WatchlistEntry, payload["entry_id"])
        return f"Remove {entry.full_name} from the {entry.list.replace('_', ' ')}" if entry else "Remove watchlist entry"

    def old_value(self, payload):
        entry = db.session.get(WatchlistEntry, payload["entry_id"])
        return entry.to_dict() if entry else None

    def apply(self, request, actor):
        entry = db.session.query(WatchlistEntry).filter_by(id=request.payload["entry_id"]).with_for_update().one()
        entry.status, entry.removed_by, entry.removed_at = "removed", request.maker_email, utcnow()
        create_audit_log("REMOVE_WATCHLIST_ENTRY", target_type="watchlist_entry", target_id=entry.id,
                         target_name=entry.full_name, description=request.payload["reason"],
                         old_value={"status": "active"}, new_value={"status": "removed", "change_request_id": request.id})
        return {"entry_id": entry.id, "status": entry.status}
