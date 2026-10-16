"""
Merging duplicate clients (FSD v0.1 KYC-10) and moving a client to another
branch (KYC-12). Both are change requests, applied only when a different person
approves.

    party.merge            {survivor_id, merged_id, reason}
    party.branch_transfer  {party_id, to_branch_id, reason}

A merge moves everything the duplicate holds (identifiers, contacts, addresses,
bank accounts, roles, links, mandate, PEP details, consents, screening history,
documents and accounts) onto the surviving record. The duplicate stays, marked
`merged` and pointing at the survivor, with its own details as they were; the
audit entry keeps a full snapshot of it. A merge is refused when both records
hold an investment account (an investor has one account) or have different
values for the same identifier.

A branch transfer moves the client, its accounts and its investor record.
Accounting entries between branches follow with the general ledger (phase 4).
"""
import hashlib
import json

from app.Approvals.handlers import Handler, register
from app.Branches.model import Branch
from app.database.database import db
from app.Documents.model import DocumentLink
from app.Parties import service
from app.Parties.model import (
    Account,
    Party,
    PartyAddress,
    PartyBankAccount,
    PartyConsent,
    PartyContact,
    PartyIdentifier,
    PartyMandate,
    PartyPepDetails,
    PartyPerson,
    PartyRelationship,
    PartyRole,
    ScreeningResult,
)
from app.Parties.normalise import ID_TYPE_LABELS
from app.utils.audit_log import create_audit_log
from app.utils.dates import today_eat, utcnow
from app.utils.http import Conflict, ValidationError


def _int(payload, key) -> int:
    value = payload.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValidationError(f"{key} is required.")
    return value


def _reason(payload) -> str:
    reason = str(payload.get("reason") or "").strip()
    if not reason:
        raise ValidationError("A reason is required.")
    return reason[:2000]


def _has_investment(party_id: int) -> bool:
    return db.session.query(Account.id).filter_by(party_id=party_id, account_type="investment").first() is not None


def _state(party: Party) -> str:
    detail = service.party_detail(party)
    detail.pop("screening", None)
    return hashlib.sha256(json.dumps(detail, sort_keys=True, default=str).encode()).hexdigest()


@register
class MergeParties(Handler):
    request_type = "party.merge"
    entity_type = "party"
    submit_permission = "party.edit"

    def entity_id(self, payload):
        return str(payload["merged_id"])

    def validate(self, payload):
        survivor = service.get_party(_int(payload, "survivor_id"))
        merged = service.get_party(_int(payload, "merged_id"))
        if survivor.id == merged.id:
            raise ValidationError("Choose two different clients.")
        for p in (survivor, merged):
            if p.status == "merged":
                raise Conflict(f"{p.party_no} has already been merged into another record.")
        if survivor.party_type != merged.party_type:
            raise ValidationError("An individual and an organisation can't be merged.")
        if _has_investment(survivor.id) and _has_investment(merged.id):
            raise Conflict(f"Both {survivor.party_no} and {merged.party_no} have an investment account; an investor "
                           "has one account, so close one of them before merging.")
        mine = {i.id_type: i.value_normalised for i in PartyIdentifier.query.filter_by(party_id=survivor.id)}
        for i in PartyIdentifier.query.filter_by(party_id=merged.id):
            if i.id_type in mine and mine[i.id_type] != i.value_normalised:
                raise Conflict(f"The two records have different {ID_TYPE_LABELS[i.id_type]}s, so they may not be the "
                               "same client. Correct one of them first.")
        return {"survivor_id": survivor.id, "merged_id": merged.id, "reason": _reason(payload)}

    def base_version(self, payload):
        a, b = db.session.get(Party, payload["survivor_id"]), db.session.get(Party, payload["merged_id"])
        return hashlib.sha256(f"{_state(a)}:{_state(b)}".encode()).hexdigest() if a and b else None

    def branch_id(self, payload):
        party = db.session.get(Party, payload["survivor_id"])
        return party.home_branch_id if party else None

    def describe(self, payload):
        a, b = db.session.get(Party, payload["survivor_id"]), db.session.get(Party, payload["merged_id"])
        if not (a and b):
            return "Merge clients"
        return f"Merge {b.party_no} {b.display_name} into {a.party_no} {a.display_name}"

    def old_value(self, payload):
        merged = db.session.get(Party, payload["merged_id"])
        return service.party_detail(merged) if merged else None

    def apply(self, request, actor):
        ids = sorted((request.payload["survivor_id"], request.payload["merged_id"]))
        locked = {p.id: p for p in db.session.query(Party).filter(Party.id.in_(ids)).order_by(Party.id).with_for_update()}
        survivor, merged = locked[request.payload["survivor_id"]], locked[request.payload["merged_id"]]
        snapshot = service.party_detail(merged)
        moved = {}

        def count(name, n):
            if n:
                moved[name] = moved.get(name, 0) + n

        count("identifiers", PartyIdentifier.query.filter_by(party_id=merged.id).update({"party_id": survivor.id}))
        have = {(c.kind, c.value_normalised or c.value) for c in PartyContact.query.filter_by(party_id=survivor.id)}
        for c in PartyContact.query.filter_by(party_id=merged.id).all():
            if (c.kind, c.value_normalised or c.value) in have:
                db.session.delete(c)  # the same number or email already on the survivor
            else:
                c.party_id, c.is_primary = survivor.id, False
                count("contacts", 1)
        count("addresses", PartyAddress.query.filter_by(party_id=merged.id).update({"party_id": survivor.id}))
        survivor_default = PartyBankAccount.query.filter_by(party_id=survivor.id, status="active",
                                                            is_default_payout=True).first()
        for b in PartyBankAccount.query.filter_by(party_id=merged.id).all():
            if survivor_default is not None:
                b.is_default_payout = False
            db.session.flush()
            b.party_id = survivor.id
            count("bank_accounts", 1)
        for r in PartyRole.query.filter_by(party_id=merged.id, status="active").all():
            if PartyRole.query.filter_by(party_id=survivor.id, role=r.role, status="active").first():
                r.status, r.ended_on = "ended", today_eat()
            else:
                r.party_id = survivor.id
                count("roles", 1)
        for rel in PartyRelationship.query.filter(
                (PartyRelationship.from_party_id == merged.id) | (PartyRelationship.to_party_id == merged.id)).all():
            new_from = survivor.id if rel.from_party_id == merged.id else rel.from_party_id
            new_to = survivor.id if rel.to_party_id == merged.id else rel.to_party_id
            clash = new_from == new_to or (rel.status == "active" and PartyRelationship.query.filter(
                PartyRelationship.id != rel.id, PartyRelationship.from_party_id == new_from,
                PartyRelationship.to_party_id == new_to, PartyRelationship.relationship == rel.relationship,
                PartyRelationship.status == "active").first() is not None)
            if clash:
                rel.status, rel.ended_on = "ended", rel.ended_on or today_eat()  # kept on the old record
            else:
                rel.from_party_id, rel.to_party_id = new_from, new_to
                count("relationships", 1)
        mandate = PartyMandate.query.filter_by(party_id=merged.id, status="active").first()
        if mandate is not None:
            if PartyMandate.query.filter_by(party_id=survivor.id, status="active").first():
                mandate.status = "ended"
            else:
                mandate.party_id = survivor.id
                count("mandate", 1)
        pep = db.session.get(PartyPepDetails, merged.id)
        if pep is not None and db.session.get(PartyPepDetails, survivor.id) is None:
            db.session.flush()
            db.session.execute(PartyPepDetails.__table__.update().where(PartyPepDetails.party_id == merged.id)
                               .values(party_id=survivor.id))
            count("pep_details", 1)
        survivor.is_pep = survivor.is_pep or merged.is_pep
        for c in PartyConsent.query.filter_by(party_id=merged.id).all():
            if c.status == "active" and PartyConsent.query.filter_by(party_id=survivor.id, purpose=c.purpose,
                                                                     status="active").first():
                c.status, c.withdrawn_at, c.withdrawn_by = "withdrawn", utcnow(), actor.email
                c.withdrawal_note = f"Merged into {survivor.party_no}, which already holds this consent."
            db.session.flush()
            c.party_id = survivor.id
            count("consents", 1)
        count("screening_results", ScreeningResult.query.filter_by(party_id=merged.id).update({"party_id": survivor.id}))
        count("documents", DocumentLink.query.filter_by(entity_type="party", entity_id=str(merged.id))
              .update({"entity_id": str(survivor.id)}))
        PartyPerson.query.filter_by(employer_party_id=merged.id).update({"employer_party_id": survivor.id})
        from app.Investors.model import Investor
        count("accounts", Account.query.filter_by(party_id=merged.id).update({"party_id": survivor.id}))
        Investor.query.filter_by(party_id=merged.id).update({"party_id": survivor.id})

        merged.status, merged.merged_into_party_id = "merged", survivor.id
        if moved.get("identifiers") and survivor.kyc_status == "verified":
            survivor.kyc_status, survivor.verified_at, survivor.verified_by = "pending_review", None, None
        db.session.flush()
        service.refresh_kyc_status(survivor)
        from app.Parties.changes import mirror_to_investor
        from app.Parties.screening import screen_party
        mirror_to_investor(survivor)
        screen_party(survivor, "identity_change", actor.email)
        create_audit_log("MERGE_PARTY", target_type="party", target_id=survivor.id, target_name=survivor.party_no,
                         description=f"{merged.party_no} {merged.display_name} merged into {survivor.party_no}: "
                                     f"{request.payload['reason']}",
                         old_value={"merged_party": snapshot},
                         new_value={"moved": moved, "change_request_id": request.id})
        return {"survivor": survivor.party_no, "merged": merged.party_no, "moved": moved}


@register
class TransferPartyBranch(Handler):
    request_type = "party.branch_transfer"
    entity_type = "party"
    submit_permission = "party.edit"

    def entity_id(self, payload):
        return str(payload["party_id"])

    def validate(self, payload):
        party = service.get_party(_int(payload, "party_id"))
        if party.status == "merged":
            raise Conflict(f"{party.party_no} was merged into another record.")
        branch = db.session.get(Branch, _int(payload, "to_branch_id"))
        if branch is None or branch.status != "active":
            raise ValidationError("to_branch_id must be an active branch.")
        if branch.id == party.home_branch_id:
            raise ValidationError(f"{party.party_no} is already in {branch.code} {branch.name}.")
        return {"party_id": party.id, "to_branch_id": branch.id, "from_branch_id": party.home_branch_id,
                "reason": _reason(payload)}

    def base_version(self, payload):
        party = db.session.get(Party, payload["party_id"])
        return str(party.home_branch_id) if party else None

    def branch_id(self, payload):
        party = db.session.get(Party, payload["party_id"])
        return party.home_branch_id if party else None

    def describe(self, payload):
        party, branch = db.session.get(Party, payload["party_id"]), db.session.get(Branch, payload["to_branch_id"])
        if not (party and branch):
            return "Branch transfer"
        return f"Move {party.party_no} {party.display_name} to {branch.code} {branch.name}"

    def old_value(self, payload):
        party = db.session.get(Party, payload["party_id"])
        return {"home_branch_id": party.home_branch_id} if party else None

    def apply(self, request, actor):
        from app.Investors.model import Investor

        party = service.lock_party(request.payload["party_id"])
        old, new = party.home_branch_id, request.payload["to_branch_id"]
        party.home_branch_id = new
        accounts = Account.query.filter_by(party_id=party.id).update({"branch_id": new})
        Investor.query.filter_by(party_id=party.id).update({"branch_id": new})
        PartyRole.query.filter_by(party_id=party.id, status="active").update({"branch_id": new})
        create_audit_log("TRANSFER_PARTY_BRANCH", target_type="party", target_id=party.id, target_name=party.party_no,
                         description=self.describe(request.payload) + f": {request.payload['reason']}",
                         old_value={"home_branch_id": old},
                         new_value={"home_branch_id": new, "accounts_moved": accounts, "change_request_id": request.id})
        return {"party_no": party.party_no, "from_branch_id": old, "to_branch_id": new, "accounts": accounts}
