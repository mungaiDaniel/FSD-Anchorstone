"""
Party change requests (maker-checker through app/Approvals).

    party.verify    mark a client's KYC verified; refused while compulsory
                    details are missing (or, later, a screening match or PEP
                    approval is open). Approved by kyc.verify.
"""
from app.Approvals.handlers import Handler, register
from app.Parties import service
from app.Parties.model import Party
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
