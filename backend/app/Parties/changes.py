"""
Editing a client (FSD v0.1 KYC-08, WA-01).

An edit is split by the setting kyc.maker_checker_fields, read when the edit is
made (default: identity, bank, payout):

    identity  names, gender, date of birth, nationality, identifiers,
              an organisation's registered name and registration date
    bank      the bank and M-Pesa accounts on file
    payout    which account interest and withdrawals are paid to
    email / phone / address   contact details (direct unless added to the setting)

Controlled groups become ONE party.change change request; the client is
unchanged until a different person approves it. Everything else saves at once
and is audited with old and new values. The same split applies to the investor
form (PATCH /investors/<id>), whose fields map onto the same groups.

A request carries the raw edit; it is cleaned and checked again (duplicates
included) at submit and at approval, and base_version refuses it if the
controlled details changed in between.
"""
import hashlib
import json

from app.database.database import db
from app.Parties import service as parties
from app.Parties.model import (
    Party,
    PartyAddress,
    PartyBankAccount,
    PartyContact,
    PartyIdentifier,
    PartyOrganisation,
    PartyPerson,
)
from app.Settings import business
from app.utils.audit_log import create_audit_log
from app.utils.dates import iso
from app.utils.http import Conflict, ValidationError

IDENTITY_PERSON = ("salutation", "first_name", "middle_name", "last_name", "gender", "date_of_birth", "nationality")
OTHER_PERSON = ("marital_status", "residency", "sector", "nature_of_business", "employer_name")
IDENTITY_ORG = ("legal_name", "registration_date")
OTHER_ORG = ("trading_name", "org_type", "sector", "nature_of_business")
TOP_FIELDS = ("classification", "risk_rating", "notes", "relationship_officer_user_id")
CONTACT_GROUP = {"email": "email", "mobile": "phone", "phone": "phone"}
# Investor-form fields and the group each belongs to.
INVESTOR_GROUPS = {"full_name": "identity", "id_number": "identity", "kra_pin": "identity",
                   "payout_method": "payout", "bank_name": "bank", "payout_account": "bank",
                   "email": "email", "phone": "phone"}
GROUP_LABELS = {"identity": "identity details", "bank": "bank details", "payout": "payout account",
                "email": "email", "phone": "phone numbers", "address": "addresses"}


def controlled_groups() -> set[str]:
    groups = set(business.get("kyc.maker_checker_fields"))
    if "bank" in groups:
        groups.add("payout")  # changing the accounts on file can change where money is paid
    return groups


# ── What is on file now, in the same shape as an edit ─────────────────────


def _person(party: Party) -> dict:
    p = db.session.get(PartyPerson, party.id)
    return {k: (iso(getattr(p, k)) if k == "date_of_birth" else getattr(p, k))
            for k in IDENTITY_PERSON + OTHER_PERSON} if p else {}


def _organisation(party: Party) -> dict:
    o = db.session.get(PartyOrganisation, party.id)
    return {k: (iso(getattr(o, k)) if k == "registration_date" else getattr(o, k))
            for k in IDENTITY_ORG + OTHER_ORG} if o else {}


def _idents(party_id: int) -> list:
    return sorted((i.id_type, i.issuing_country, i.value_display, iso(i.issued_on), iso(i.expires_on))
                  for i in PartyIdentifier.query.filter_by(party_id=party_id))


def _banks(party_id: int) -> list:
    return sorted((b.kind, b.bank_name, b.branch_name, b.account_no, b.account_name)
                  for b in PartyBankAccount.query.filter_by(party_id=party_id, status="active"))


def _default_payout(party_id: int):
    b = PartyBankAccount.query.filter_by(party_id=party_id, status="active", is_default_payout=True).first()
    return (b.kind, b.bank_name, b.account_no) if b else None


def _contacts(party_id: int, group: str) -> list:
    return sorted((c.kind, c.value, c.is_primary) for c in PartyContact.query.filter_by(party_id=party_id)
                  if CONTACT_GROUP[c.kind] == group)


def _addresses(party_id: int) -> list:
    return sorted((a.kind, a.line1, a.line2, a.town, a.county, a.country)
                  for a in PartyAddress.query.filter_by(party_id=party_id))


def fingerprint(party: Party, groups) -> str:
    """The current state of the controlled details a request touches (its base_version)."""
    state = {}
    if "identity" in groups:
        state["identity"] = [{k: v for k, v in _person(party).items() if k in IDENTITY_PERSON},
                             {k: v for k, v in _organisation(party).items() if k in IDENTITY_ORG},
                             _idents(party.id), party.display_name]
    if "bank" in groups or "payout" in groups:
        state["bank"] = [_banks(party.id), _default_payout(party.id)]
    for g in ("email", "phone"):
        if g in groups:
            state[g] = _contacts(party.id, g)
    if "address" in groups:
        state["address"] = _addresses(party.id)
    return hashlib.sha256(json.dumps(state, sort_keys=True, default=str).encode()).hexdigest()


# ── Splitting an edit ─────────────────────────────────────────────────────


def _clean_fields(fields: dict, cleaner, keys) -> dict:
    cleaned = cleaner({**fields, **{k: fields.get(k) for k in keys}})
    return {k: (iso(cleaned[k]) if k in ("date_of_birth", "registration_date") else cleaned[k]) for k in keys}


def split_party_edit(party: Party, body: dict) -> tuple[dict, dict]:
    """(direct, controlled): the parts of a PATCH /parties/<id> body that changed, by group."""
    groups = controlled_groups()
    direct, controlled = {}, {}

    def put(group: str, key: str, value):
        target = controlled if group in groups else direct
        target.setdefault("groups", set()).add(group)
        target[key] = value

    if party.party_type == "person" and isinstance(body.get("person"), dict):
        now = _person(party)
        new = _clean_fields({**now, **body["person"]}, parties.clean_person, IDENTITY_PERSON + OTHER_PERSON)
        for k, v in new.items():
            if k in body["person"] and v != now.get(k):
                put("identity" if k in IDENTITY_PERSON else "other", f"person.{k}", body["person"][k])
    if party.party_type == "organisation" and isinstance(body.get("organisation"), dict):
        now = _organisation(party)
        new = _clean_fields({**now, **body["organisation"]}, parties.clean_organisation, IDENTITY_ORG + OTHER_ORG)
        for k, v in new.items():
            if k in body["organisation"] and v != now.get(k):
                put("identity" if k in IDENTITY_ORG else "other", f"organisation.{k}", body["organisation"][k])
    if "identifiers" in body:
        new = parties.clean_identifiers(parties._list(body, "identifiers"), party.party_type)
        if sorted((i["id_type"], i["issuing_country"], i["value_display"], iso(i["issued_on"]), iso(i["expires_on"]))
                  for i in new) != _idents(party.id):
            put("identity", "identifiers", body["identifiers"])
    if "bank_accounts" in body:
        new = parties.clean_bank_accounts(parties._list(body, "bank_accounts"))
        accounts = sorted((b["kind"], b["bank_name"], b["branch_name"], b["account_no"], b["account_name"]) for b in new)
        default = next(((b["kind"], b["bank_name"], b["account_no"]) for b in new if b["is_default_payout"]), None)
        if accounts != _banks(party.id):
            put("bank", "bank_accounts", body["bank_accounts"])
        elif default != _default_payout(party.id):
            put("payout", "bank_accounts", body["bank_accounts"])
    if "contacts" in body:
        new = parties.clean_contacts(parties._list(body, "contacts"))
        for group in ("email", "phone"):
            mine = [c for c in new if CONTACT_GROUP[c["kind"]] == group]
            if sorted((c["kind"], c["value"], c["is_primary"]) for c in mine) != _contacts(party.id, group):
                put(group, f"contacts.{group}", [c for c in body["contacts"] if CONTACT_GROUP.get(c.get("kind")) == group])
    if "addresses" in body:
        new = parties.clean_addresses(parties._list(body, "addresses"))
        if sorted((a["kind"], a["line1"], a["line2"], a["town"], a["county"], a["country"]) for a in new) != \
                _addresses(party.id):
            put("address", "addresses", body["addresses"])
    for key in TOP_FIELDS:
        if key in body and body[key] != getattr(party, key):
            put("other", key, body[key])
    if "home_branch_id" in body and body["home_branch_id"] != party.home_branch_id:
        raise ValidationError("Moving a client to another branch is a branch transfer, made from the client view.")
    for part in (direct, controlled):
        if "groups" in part:
            part["groups"] = sorted(part["groups"])
    return direct, controlled


# ── Applying ──────────────────────────────────────────────────────────────


def apply_party_changes(party: Party, changes: dict, actor: str) -> dict:
    """Write a split edit (direct part, or an approved request). Returns {old, new} for the audit."""
    old = snapshot(party)
    person = {k.split(".", 1)[1]: v for k, v in changes.items() if k.startswith("person.")}
    if person:
        row = db.session.get(PartyPerson, party.id)
        cleaned = parties.clean_person({**_person(party), **person})
        for k in person:
            setattr(row, k, cleaned[k])
        if {"first_name", "middle_name", "last_name"} & set(person):
            party.display_name = " ".join(p for p in (row.first_name, row.middle_name, row.last_name) if p)
            row.name_needs_review = False
    org = {k.split(".", 1)[1]: v for k, v in changes.items() if k.startswith("organisation.")}
    if org:
        row = db.session.get(PartyOrganisation, party.id)
        cleaned = parties.clean_organisation({**_organisation(party), **org})
        for k in org:
            setattr(row, k, cleaned[k])
        party.display_name = row.legal_name
    if "identifiers" in changes:
        new = parties.clean_identifiers(parties._list(changes, "identifiers"), party.party_type)
        parties.assert_identifiers_free(new, exclude_party_id=party.id)
        PartyIdentifier.query.filter_by(party_id=party.id).delete()
        db.session.flush()
        for i in new:
            db.session.add(PartyIdentifier(party_id=party.id, **i))
    if "bank_accounts" in changes:
        new = parties.clean_bank_accounts(parties._list(changes, "bank_accounts"))
        current = PartyBankAccount.query.filter_by(party_id=party.id, status="active").all()
        for b in current:
            b.status, b.is_default_payout = "ended", False  # kept for the record
        db.session.flush()
        for b in new:
            db.session.add(PartyBankAccount(party_id=party.id, status="active", **b))
    for group in ("email", "phone"):
        if f"contacts.{group}" in changes:
            new = parties.clean_contacts(changes[f"contacts.{group}"])
            for c in PartyContact.query.filter_by(party_id=party.id).all():
                if CONTACT_GROUP[c.kind] == group:
                    db.session.delete(c)
            db.session.flush()
            for c in new:
                db.session.add(PartyContact(party_id=party.id, **c))
    if "addresses" in changes:
        new = parties.clean_addresses(parties._list(changes, "addresses"))
        PartyAddress.query.filter_by(party_id=party.id).delete()
        for a in new:
            db.session.add(PartyAddress(party_id=party.id, **a))
    if "classification" in changes:
        party.classification = parties._text(changes, "classification", 40)
    if "risk_rating" in changes:
        party.risk_rating = parties._choice(changes, "risk_rating", ("low", "medium", "high"))
    if "notes" in changes:
        party.notes = parties._text(changes, "notes", 2000)
    if "relationship_officer_user_id" in changes:
        party.relationship_officer_user_id = changes["relationship_officer_user_id"] or None
    db.session.flush()

    identity_changed = "identity" in changes.get("groups", [])
    if identity_changed and party.kyc_status == "verified":
        party.kyc_status, party.verified_at, party.verified_by = "pending_review", None, None  # re-verify
    parties.refresh_kyc_status(party)
    mirror_to_investor(party)
    if identity_changed:
        from app.Parties.screening import screen_party
        screen_party(party, "identity_change", actor)
    db.session.flush()
    return {"old": old, "new": snapshot(party)}


def mirror_to_investor(party: Party) -> None:
    """Keep the investor's mirrored columns (read by statements and reports) in step with the party."""
    from app.Investors.model import Investor
    from app.Parties.investors import investor_fields_from_party

    investor = Investor.query.filter_by(party_id=party.id).first()
    if investor is None:
        return
    for k, v in investor_fields_from_party(party).items():
        if k == "kra_pin" and v:
            v = v.upper()
        setattr(investor, k, v)


def snapshot(party: Party) -> dict:
    return {"display_name": party.display_name, "person": _person(party), "organisation": _organisation(party),
            "identifiers": _idents(party.id), "bank_accounts": _banks(party.id),
            "default_payout": _default_payout(party.id), "email": _contacts(party.id, "email"),
            "phone": _contacts(party.id, "phone"), "addresses": _addresses(party.id),
            "classification": party.classification, "risk_rating": party.risk_rating, "notes": party.notes}


def describe_groups(groups) -> str:
    return ", ".join(GROUP_LABELS.get(g, g) for g in groups if g != "other")


# ── The edit itself ───────────────────────────────────────────────────────


def edit_party(party_id: int, body: dict, actor_user) -> dict:
    """PATCH /parties/<id>: save the direct part, submit the controlled part. Returns what happened."""
    from app.Approvals import service as approvals

    party = parties.lock_party(party_id)
    if party.status == "merged":
        raise Conflict("This client was merged into another record.")
    direct, controlled = split_party_edit(party, body)
    saved = None
    if direct:
        audit = apply_party_changes(party, direct, actor_user.email)
        create_audit_log("UPDATE_PARTY", target_type="party", target_id=party.id, target_name=party.party_no,
                         description="Saved directly: " + (describe_groups(direct["groups"]) or "other details"),
                         old_value=audit["old"], new_value=audit["new"])
        saved = direct["groups"]
    cr = None
    if controlled:
        cr = approvals.submit("party.change", {"party_id": party.id, "changes": controlled}, actor_user,
                              body.get("reason"), commit=False)
    db.session.commit()
    return {"saved": saved or [], "change_request": cr}
