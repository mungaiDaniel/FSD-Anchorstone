"""
Parties: one record per person or organisation (FSD v0.1 §4, KYC-01 … KYC-12).

    create_party      individual or organisation with identifiers, contacts,
                      addresses, bank accounts and roles (KYC-01, 02, 11)
    add_relationship  next of kin, director, shareholder, signatory, guarantor
                      (with the amount committed), agent, related party (KYC-03)
    set_mandate       signing rule for an organisation or joint holding
    request_verification  KYC verification is a change request (party.verify)

Identifiers are unique across all branches; a second party with the same ID
number, passport, KRA PIN or registration number is refused, naming the
party that already has it (KYC-04). The database index backs this up.
"""
from decimal import Decimal

from sqlalchemy import func, or_

from app.Approvals import service as approvals
from app.Branches.model import HEAD_OFFICE_ID, Branch
from app.database.database import db
from app.Parties.model import (
    ADDRESS_KINDS,
    BANK_KINDS,
    CONTACT_KINDS,
    GENDERS,
    KYC_STATUSES,
    MANDATE_RULES,
    MARITAL_STATUSES,
    ORG_TYPES,
    PARTY_TYPES,
    RELATIONSHIP_ROLE,
    RELATIONSHIPS,
    RESIDENCIES,
    RISK_RATINGS,
    ROLES,
    Party,
    PartyAddress,
    PartyBankAccount,
    PartyContact,
    PartyIdentifier,
    PartyMandate,
    PartyOrganisation,
    PartyPerson,
    PartyRelationship,
    PartyRole,
    PEP_RELATIONSHIPS,
    PartyPepDetails,
    ScreeningResult,
    party_no_seq,
)
from app.Parties.normalise import ID_TYPE_LABELS, ID_TYPES, normalise_email, normalise_identifier, normalise_phone
from app.Settings import business
from app.utils.audit_log import create_audit_log
from app.utils.dates import parse_date, today_eat, utcnow
from app.utils.http import Conflict, NotFound, ValidationError
from app.utils.money import parse_amount

PERSON_ID_TYPES = ("national_id", "passport", "alien_id")
# Roles that come from another record, never set directly on a party.
DERIVED_ROLES = ("investor",)


# ── Cleaning input ─────────────────────────────────────────────────────────


def _text(data: dict, field: str, max_len: int, *, required: bool = False, label: str | None = None) -> str | None:
    raw = data.get(field)
    value = str(raw).strip() if raw is not None else ""
    if required and not value:
        raise ValidationError(f"{label or field} is required.")
    if len(value) > max_len:
        raise ValidationError(f"{label or field} must be at most {max_len} characters.")
    return value or None


def _choice(data: dict, field: str, choices, *, required: bool = False, default=None) -> str | None:
    raw = data.get(field)
    value = str(raw).strip().lower() if raw not in (None, "") else None
    if value is None:
        if required and default is None:
            raise ValidationError(f"{field} is required.")
        return default
    if value not in choices:
        raise ValidationError(f"{field} must be one of: {', '.join(choices)}.")
    return value


def _country(data: dict, field: str) -> str:
    value = (str(data.get(field) or "KE")).strip().upper()
    if len(value) != 2 or not value.isalpha():
        raise ValidationError(f"{field} must be a two-letter country code.")
    return value


def _list(data: dict, field: str) -> list:
    value = data.get(field) or []
    if not isinstance(value, list) or not all(isinstance(v, dict) for v in value):
        raise ValidationError(f"{field} must be a list of objects.")
    return value


def clean_person(data: dict) -> dict:
    values = {
        "salutation": _text(data, "salutation", 20),
        "first_name": _text(data, "first_name", 80),
        "middle_name": _text(data, "middle_name", 80),
        "last_name": _text(data, "last_name", 80),
        "gender": _choice(data, "gender", GENDERS),
        "date_of_birth": parse_date(data.get("date_of_birth"), "date_of_birth", required=False),
        "marital_status": _choice(data, "marital_status", MARITAL_STATUSES),
        "nationality": _country(data, "nationality"),
        "residency": _choice(data, "residency", RESIDENCIES, default="local"),
        "sector": _text(data, "sector", 100),
        "nature_of_business": _text(data, "nature_of_business", 200),
        "employer_name": _text(data, "employer_name", 150),
    }
    if not values["first_name"] and not values["last_name"]:
        raise ValidationError("A first or last name is required.")
    if values["date_of_birth"] and values["date_of_birth"] > today_eat():
        raise ValidationError("date_of_birth can't be in the future.")
    return values


def clean_organisation(data: dict) -> dict:
    values = {
        "legal_name": _text(data, "legal_name", 200, required=True, label="Registered name"),
        "trading_name": _text(data, "trading_name", 200),
        "registration_date": parse_date(data.get("registration_date"), "registration_date", required=False),
        "org_type": _choice(data, "org_type", ORG_TYPES, required=True),
        "sector": _text(data, "sector", 100),
        "nature_of_business": _text(data, "nature_of_business", 200),
    }
    if values["registration_date"] and values["registration_date"] > today_eat():
        raise ValidationError("registration_date can't be in the future.")
    return values


def clean_identifiers(items: list, party_type: str) -> list[dict]:
    out, seen = [], set()
    for item in items:
        id_type = _choice(item, "id_type", ID_TYPES, required=True)
        if party_type == "organisation" and id_type in PERSON_ID_TYPES:
            raise ValidationError(f"An organisation can't have a {ID_TYPE_LABELS[id_type]}.")
        if party_type == "person" and id_type == "company_reg_no":
            raise ValidationError("An individual can't have a company registration number.")
        display = _text(item, "value", 50, required=True, label=ID_TYPE_LABELS[id_type])
        normalised = normalise_identifier(id_type, display)
        if not normalised:
            raise ValidationError(f"{ID_TYPE_LABELS[id_type]} is not valid.")
        if id_type in seen:
            raise ValidationError(f"Only one {ID_TYPE_LABELS[id_type]} per party.")
        seen.add(id_type)
        out.append({"id_type": id_type, "issuing_country": _country(item, "issuing_country"),
                    "value_display": display, "value_normalised": normalised,
                    "issued_on": parse_date(item.get("issued_on"), "issued_on", required=False),
                    "expires_on": parse_date(item.get("expires_on"), "expires_on", required=False)})
    return out


def clean_contacts(items: list) -> list[dict]:
    out = []
    for item in items:
        kind = _choice(item, "kind", CONTACT_KINDS, required=True)
        value = _text(item, "value", 150, required=True, label=kind)
        if kind == "email":
            normalised = normalise_email(value)
            if "@" not in normalised or "." not in normalised.split("@")[-1]:
                raise ValidationError(f"{value} is not a valid email.")
        else:
            normalised = normalise_phone(value)  # unreadable numbers are kept, flagged for review
        out.append({"kind": kind, "value": value, "value_normalised": normalised,
                    "is_primary": bool(item.get("is_primary"))})
    for kind in CONTACT_KINDS:
        rows = [c for c in out if c["kind"] == kind]
        if rows and not any(c["is_primary"] for c in rows):
            rows[0]["is_primary"] = True
        if sum(c["is_primary"] for c in rows) > 1:
            raise ValidationError(f"Only one primary {kind}.")
    return out


def clean_addresses(items: list) -> list[dict]:
    return [{"kind": _choice(a, "kind", ADDRESS_KINDS, required=True),
             "line1": _text(a, "line1", 200, required=True, label="Address"),
             "line2": _text(a, "line2", 200), "town": _text(a, "town", 100), "county": _text(a, "county", 100),
             "country": _country(a, "country")} for a in items]


def clean_bank_accounts(items: list) -> list[dict]:
    out = []
    for b in items:
        kind = _choice(b, "kind", BANK_KINDS, required=True)
        row = {"kind": kind, "bank_name": _text(b, "bank_name", 100), "branch_name": _text(b, "branch_name", 100),
               "account_no": _text(b, "account_no", 100, required=True, label="Account number"),
               "account_name": _text(b, "account_name", 150), "is_default_payout": bool(b.get("is_default_payout"))}
        if kind == "bank" and not row["bank_name"]:
            raise ValidationError("bank_name is required for a bank account.")
        out.append(row)
    if sum(b["is_default_payout"] for b in out) > 1:
        raise ValidationError("Only one default payout account.")
    if out and not any(b["is_default_payout"] for b in out):
        out[0]["is_default_payout"] = True
    return out


# ── Duplicates (KYC-04) ────────────────────────────────────────────────────


def assert_identifiers_free(identifiers: list[dict], exclude_party_id: int | None = None) -> None:
    for ident in identifiers:
        q = db.session.query(PartyIdentifier, Party).join(Party, Party.id == PartyIdentifier.party_id).filter(
            PartyIdentifier.id_type == ident["id_type"],
            PartyIdentifier.issuing_country == ident["issuing_country"],
            PartyIdentifier.value_normalised == ident["value_normalised"])
        if exclude_party_id is not None:
            q = q.filter(PartyIdentifier.party_id != exclude_party_id)
        clash = q.first()
        if clash:
            party = clash[1]
            raise Conflict(f"{ID_TYPE_LABELS[ident['id_type']]} already registered to {party.party_no} "
                           f"({party.display_name}).")


def duplicate_warnings(contacts: list[dict], exclude_party_id: int | None = None) -> list[dict]:
    """KYC-05: phones and emails already used by another client. A warning, never a block."""
    out, seen = [], set()
    for c in contacts:
        value = c.get("value_normalised")
        if not value:
            continue
        kinds = ("email",) if c["kind"] == "email" else ("mobile", "phone")
        q = db.session.query(PartyContact, Party).join(Party, Party.id == PartyContact.party_id).filter(
            PartyContact.kind.in_(kinds), PartyContact.value_normalised == value, Party.status != "merged")
        if exclude_party_id is not None:
            q = q.filter(Party.id != exclude_party_id)
        for contact, party in q.order_by(Party.id).all():
            key = (contact.kind, value, party.id)
            if key in seen:
                continue
            seen.add(key)
            label = "email" if c["kind"] == "email" else "phone number"
            out.append({"kind": c["kind"], "value": c["value"], "party": party.summary(),
                        "message": f"This {label} already belongs to {party.party_no} ({party.display_name})."})
    return out


def check_duplicates(data: dict, exclude_party_id: int | None = None) -> dict:
    """What capture would refuse (identifiers) and what it only warns about (phones, emails)."""
    party_type = data.get("party_type") if data.get("party_type") in PARTY_TYPES else "person"
    conflicts = []
    for ident in clean_identifiers(_list(data, "identifiers"), party_type):
        try:
            assert_identifiers_free([ident], exclude_party_id)
        except Conflict as e:
            existing = find_parties_by_identifier(ident["id_type"], ident["value_display"])
            conflicts.append({"id_type": ident["id_type"], "value": ident["value_display"], "message": e.message,
                              "party": existing.summary() if existing else None})
    return {"conflicts": conflicts, "warnings": duplicate_warnings(clean_contacts(_list(data, "contacts")),
                                                                   exclude_party_id)}


# ── Reading ────────────────────────────────────────────────────────────────


def get_party(party_id: int) -> Party:
    party = db.session.get(Party, party_id)
    if party is None:
        raise NotFound("Client not found.")
    return party


def lock_party(party_id: int) -> Party:
    party = db.session.query(Party).filter(Party.id == party_id).with_for_update().one_or_none()
    if party is None:
        raise NotFound("Client not found.")
    return party


def _rows(model, party_id: int, *, active_only: bool = False):
    q = model.query.filter(model.party_id == party_id)
    if active_only and hasattr(model, "status"):
        q = q.filter(model.status == "active")
    return q.order_by(model.id).all()


def relationships_of(party_id: int) -> list[dict]:
    """Both directions: who relates to this party (its directors, kin …) and whom it relates to."""
    rows = PartyRelationship.query.filter(or_(PartyRelationship.from_party_id == party_id,
                                              PartyRelationship.to_party_id == party_id)).order_by(PartyRelationship.id).all()
    others = {p.id: p for p in Party.query.filter(Party.id.in_(
        {r.from_party_id for r in rows} | {r.to_party_id for r in rows})).all()} if rows else {}
    out = []
    for r in rows:
        incoming = r.to_party_id == party_id
        other = others[r.from_party_id if incoming else r.to_party_id]
        out.append({**r.to_dict(), "direction": "incoming" if incoming else "outgoing", "party": other.summary()})
    return out


def missing_fields(party: Party) -> list[str]:
    """Compulsory details still missing for the party's type (kyc.required_fields.*)."""
    idents = {i.id_type for i in PartyIdentifier.query.filter_by(party_id=party.id)}
    contacts = {c.kind for c in PartyContact.query.filter_by(party_id=party.id)}
    addresses = {a.kind for a in PartyAddress.query.filter_by(party_id=party.id)}
    incoming = PartyRelationship.query.filter_by(to_party_id=party.id, status="active").all()
    if party.party_type == "person":
        required = business.get("kyc.required_fields.person")
        p = party.person
        have = {
            "name": bool(p and p.first_name and p.last_name),
            "id_document": bool(idents & set(PERSON_ID_TYPES)),
            "kra_pin": "kra_pin" in idents,
            "date_of_birth": bool(p and p.date_of_birth),
            "mobile": "mobile" in contacts,
            "physical_address": bool(addresses & {"home", "business"}),
            "next_of_kin": any(r.relationship == "next_of_kin" for r in incoming),
        }
    else:
        required = business.get("kyc.required_fields.organisation")
        o = party.organisation
        directors = [r.from_party_id for r in incoming if r.relationship == "director"]
        director_ids = {i.party_id for i in PartyIdentifier.query.filter(
            PartyIdentifier.party_id.in_(directors), PartyIdentifier.id_type.in_(PERSON_ID_TYPES))} if directors else set()
        have = {
            "legal_name": bool(o and o.legal_name),
            "registration_no": "company_reg_no" in idents,
            "kra_pin": "kra_pin" in idents,
            "registration_date": bool(o and o.registration_date),
            "director_with_id": bool(director_ids),
            "phone": bool(contacts & {"mobile", "phone"}),
            "physical_address": bool(addresses & {"business", "registered"}),
        }
    return [f for f in required if not have.get(f, False)]


def party_detail(party: Party) -> dict:
    pep = db.session.get(PartyPepDetails, party.id)
    last = (ScreeningResult.query.filter_by(party_id=party.id)
            .order_by(ScreeningResult.screened_at.desc(), ScreeningResult.id.desc()).first())
    return {
        **party.to_dict(),
        "pep": pep.to_dict() if pep else None,
        "screening": {"last": last.to_dict() if last else None,
                      "pending": ScreeningResult.query.filter_by(party_id=party.id, review_status="pending").count()},
        "verification_blockers": verification_blockers(party),
        "identifiers": [i.to_dict() for i in _rows(PartyIdentifier, party.id)],
        "contacts": [c.to_dict() for c in _rows(PartyContact, party.id)],
        "addresses": [a.to_dict() for a in _rows(PartyAddress, party.id)],
        "bank_accounts": [b.to_dict() for b in _rows(PartyBankAccount, party.id, active_only=True)],
        "roles": [r.to_dict() for r in _rows(PartyRole, party.id, active_only=True)],
        "relationships": relationships_of(party.id),
        "mandate": next((m.to_dict() for m in _rows(PartyMandate, party.id, active_only=True)), None),
        "missing_fields": missing_fields(party),
    }


def list_parties(search: str | None, party_type: str | None, kyc_status: str | None, role: str | None,
                 page: int, per_page: int) -> dict:
    q = Party.query.filter(Party.status != "merged")
    if party_type in PARTY_TYPES:
        q = q.filter(Party.party_type == party_type)
    if kyc_status in KYC_STATUSES:
        q = q.filter(Party.kyc_status == kyc_status)
    if role in ROLES:
        q = q.filter(Party.id.in_(db.session.query(PartyRole.party_id).filter(
            PartyRole.role == role, PartyRole.status == "active")))
    if search and search.strip():
        term = search.strip()
        like = f"%{term}%"
        conditions = [Party.display_name.ilike(like), Party.party_no.ilike(like),
                      Party.id.in_(db.session.query(PartyContact.party_id).filter(PartyContact.value.ilike(like)))]
        ident = normalise_identifier("national_id", term)
        if ident:
            conditions.append(Party.id.in_(db.session.query(PartyIdentifier.party_id).filter(
                PartyIdentifier.value_normalised.like(f"%{ident}%"))))
        phone = normalise_phone(term)
        if phone:
            conditions.append(Party.id.in_(db.session.query(PartyContact.party_id).filter(
                PartyContact.value_normalised == phone)))
        q = q.filter(or_(*conditions))
    total = q.count()
    rows = q.order_by(Party.display_name.asc(), Party.id.asc()).limit(per_page).offset((page - 1) * per_page).all()
    roles = {}
    if rows:
        for r in PartyRole.query.filter(PartyRole.party_id.in_([p.id for p in rows]), PartyRole.status == "active"):
            roles.setdefault(r.party_id, []).append(r.role)
    primary = {}
    if rows:
        for c in PartyContact.query.filter(PartyContact.party_id.in_([p.id for p in rows]), PartyContact.is_primary):
            primary.setdefault(c.party_id, {})[c.kind] = c.value
    return {"items": [{**p.summary(), "home_branch_id": p.home_branch_id, "roles": sorted(roles.get(p.id, [])),
                       "email": primary.get(p.id, {}).get("email"),
                       "phone": primary.get(p.id, {}).get("mobile") or primary.get(p.id, {}).get("phone")}
                      for p in rows],
            "total": total, "page": page, "per_page": per_page}


# ── Writing ────────────────────────────────────────────────────────────────


def _display_name(person: dict | None, organisation: dict | None) -> str:
    if organisation:
        return organisation["legal_name"]
    return " ".join(p for p in (person["first_name"], person["middle_name"], person["last_name"]) if p)


def _branch(data: dict) -> int:
    branch_id = data.get("home_branch_id") or HEAD_OFFICE_ID
    branch = db.session.get(Branch, branch_id) if isinstance(branch_id, int) else None
    if branch is None or branch.status != "active":
        raise ValidationError("home_branch_id must be an active branch.")
    return branch.id


def refresh_kyc_status(party: Party) -> None:
    """incomplete ↔ pending_review as compulsory details come and go; verified stays until re-verification."""
    if party.kyc_status != "verified":
        db.session.flush()
        party.kyc_status = "pending_review" if not missing_fields(party) else "incomplete"


def add_role(party: Party, role: str, branch_id: int | None = None) -> PartyRole:
    existing = PartyRole.query.filter_by(party_id=party.id, role=role, status="active").first()
    if existing:
        return existing
    row = PartyRole(party_id=party.id, role=role, status="active", started_on=today_eat(),
                    branch_id=branch_id or party.home_branch_id)
    db.session.add(row)
    return row


def insert_party(*, party_type: str, person: dict | None, organisation: dict | None, identifiers: list[dict],
                 contacts: list[dict], addresses: list[dict], bank_accounts: list[dict], actor: str,
                 home_branch_id: int = HEAD_OFFICE_ID, display_name: str | None = None, **extra) -> Party:
    """Insert a party and its detail rows (no checks, no audit, no commit)."""
    number = db.session.execute(party_no_seq.next_value()).scalar()
    party = Party(party_no=f"P-{number:07d}", party_type=party_type,
                  display_name=display_name or _display_name(person, organisation), home_branch_id=home_branch_id,
                  created_at=utcnow(), created_by=actor, status="active", kyc_status="incomplete", **extra)
    db.session.add(party)
    db.session.flush()
    if person is not None:
        db.session.add(PartyPerson(party_id=party.id, **person))
    if organisation is not None:
        db.session.add(PartyOrganisation(party_id=party.id, **organisation))
    for row in identifiers:
        db.session.add(PartyIdentifier(party_id=party.id, **row))
    for row in contacts:
        db.session.add(PartyContact(party_id=party.id, **row))
    for row in addresses:
        db.session.add(PartyAddress(party_id=party.id, **row))
    for row in bank_accounts:
        db.session.add(PartyBankAccount(party_id=party.id, status="active", **row))
    db.session.flush()
    return party


def create_party(data: dict, actor: str, *, commit: bool = True) -> Party:
    """A full or "lite" party (next of kin, directors: a name and a phone are enough to start)."""
    party_type = _choice(data, "party_type", PARTY_TYPES, required=True)
    if party_type == "person":
        person, organisation = clean_person(data.get("person") or {}), None
    else:
        person, organisation = None, clean_organisation(data.get("organisation") or {})
    identifiers = clean_identifiers(_list(data, "identifiers"), party_type)
    contacts = clean_contacts(_list(data, "contacts"))
    addresses = clean_addresses(_list(data, "addresses"))
    bank_accounts = clean_bank_accounts(_list(data, "bank_accounts"))
    roles = data.get("roles") or []
    if not isinstance(roles, list) or any(r not in ROLES for r in roles):
        raise ValidationError(f"roles must be drawn from: {', '.join(ROLES)}.")
    if any(r in DERIVED_ROLES for r in roles):
        raise ValidationError("The investor role comes with an investment account; add one from the client view.")
    risk = _choice(data, "risk_rating", RISK_RATINGS)
    assert_identifiers_free(identifiers)

    party = insert_party(party_type=party_type, person=person, organisation=organisation, identifiers=identifiers,
                         contacts=contacts, addresses=addresses, bank_accounts=bank_accounts, actor=actor,
                         home_branch_id=_branch(data), classification=_text(data, "classification", 40),
                         risk_rating=risk, notes=_text(data, "notes", 2000),
                         relationship_officer_user_id=data.get("relationship_officer_user_id") or None)
    for role in roles:
        add_role(party, role)
    refresh_kyc_status(party)
    party.warnings = duplicate_warnings(contacts, exclude_party_id=party.id)
    from app.Parties.screening import screen_party
    screen_party(party, "onboarding", actor)
    db.session.flush()
    create_audit_log("CREATE_PARTY", target_type="party", target_id=party.id, target_name=party.party_no,
                     description=f"Created {party.party_type} {party.display_name}.", new_value=party_detail(party))
    if commit:
        db.session.commit()
    return party


def add_relationship(party_id: int, data: dict, actor: str) -> PartyRelationship:
    """Link a related party to this one. The related party is reused (related_party_id) or created as a lite party."""
    party = lock_party(party_id)
    if party.status == "merged":
        raise Conflict("This client was merged into another record.")
    relationship = _choice(data, "relationship", RELATIONSHIPS, required=True)
    if relationship in ("director", "shareholder") and party.party_type != "organisation":
        raise ValidationError(f"Only an organisation can have a {relationship}.")

    if data.get("related_party_id"):
        related = get_party(int(data["related_party_id"]))
        if related.status == "merged":
            raise Conflict(f"{related.party_no} was merged into another record.")
    else:
        spec = data.get("related") or {}
        related = create_party({**spec, "party_type": spec.get("party_type") or "person", "roles": []}, actor,
                               commit=False)
    if related.id == party.id:
        raise ValidationError("A client can't be related to itself.")

    exists = PartyRelationship.query.filter_by(from_party_id=related.id, to_party_id=party.id,
                                               relationship=relationship, status="active").first()
    if exists:
        raise Conflict(f"{related.display_name} is already recorded as {relationship.replace('_', ' ')}.")

    committed = None
    if relationship == "guarantor_of":
        committed = parse_amount(data.get("committed_amount"), "committed_amount")
    elif data.get("committed_amount") not in (None, ""):
        raise ValidationError("committed_amount applies to guarantors only.")
    share = None
    if data.get("share_pct") not in (None, ""):
        if relationship != "shareholder":
            raise ValidationError("share_pct applies to shareholders only.")
        try:
            share = Decimal(str(data["share_pct"]).strip())
        except ArithmeticError:
            raise ValidationError("share_pct must be a percentage.")
        if not Decimal(0) < share <= Decimal(100) or share != share.quantize(Decimal("0.0001")):
            raise ValidationError("share_pct must be above 0 and at most 100, with up to 4 decimal places.")
    signatory_list = None
    if relationship == "signatory" and data.get("signatory_list"):
        signatory_list = str(data["signatory_list"]).strip().upper()
        if signatory_list not in ("A", "B"):
            raise ValidationError("signatory_list must be A or B.")

    row = PartyRelationship(from_party_id=related.id, to_party_id=party.id, relationship=relationship,
                            share_pct=share, kin_relationship=_text(data, "kin_relationship", 50),
                            signatory_list=signatory_list, committed_amount=committed, status="active",
                            started_on=today_eat(), created_by=actor)
    db.session.add(row)
    if relationship in RELATIONSHIP_ROLE:
        add_role(related, RELATIONSHIP_ROLE[relationship])
    refresh_kyc_status(party)
    db.session.flush()
    create_audit_log("ADD_PARTY_RELATIONSHIP", target_type="party", target_id=party.id, target_name=party.party_no,
                     description=f"{related.party_no} {related.display_name} added as {relationship}.",
                     new_value=row.to_dict())
    db.session.commit()
    return row


def end_relationship(party_id: int, relationship_id: int, actor: str) -> PartyRelationship:
    party = lock_party(party_id)
    row = db.session.get(PartyRelationship, relationship_id)
    if row is None or party_id not in (row.from_party_id, row.to_party_id):
        raise NotFound("Relationship not found.")
    if row.status != "active":
        raise Conflict("This relationship has already ended.")
    row.status, row.ended_on = "ended", today_eat()
    refresh_kyc_status(party)
    create_audit_log("END_PARTY_RELATIONSHIP", target_type="party", target_id=party.id, target_name=party.party_no,
                     old_value={"status": "active"}, new_value=row.to_dict())
    db.session.commit()
    return row


def set_mandate(party_id: int, data: dict, actor: str) -> PartyMandate:
    party = lock_party(party_id)
    rule = _choice(data, "rule", MANDATE_RULES, required=True)
    description = _text(data, "description", 2000)
    if rule == "custom" and not description:
        raise ValidationError("Describe a custom signing rule.")
    current = PartyMandate.query.filter_by(party_id=party.id, status="active").first()
    old = current.to_dict() if current else None
    if current:
        current.status = "ended"
        db.session.flush()
    row = PartyMandate(party_id=party.id, rule=rule, description=description, effective_from=today_eat(),
                       status="active", created_by=actor)
    db.session.add(row)
    db.session.flush()
    create_audit_log("SET_PARTY_MANDATE", target_type="party", target_id=party.id, target_name=party.party_no,
                     old_value=old, new_value=row.to_dict())
    db.session.commit()
    return row


def verification_blockers(party: Party) -> list[str]:
    """Why KYC can't be verified yet (empty = it can)."""
    reasons = []
    if party.status != "active":
        reasons.append(f"The client is {party.status}.")
    missing = missing_fields(party)
    if missing:
        reasons.append("Missing compulsory details: " + ", ".join(m.replace("_", " ") for m in missing) + ".")
    if ScreeningResult.query.filter_by(party_id=party.id, review_status="pending").first():
        reasons.append("A possible watchlist match must be reviewed first.")
    if party.is_pep:
        pep = db.session.get(PartyPepDetails, party.id)
        if pep is None:
            reasons.append("The client is a PEP: record the PEP details.")
        elif pep.status != "approved":
            reasons.append("The client is a PEP: senior approval of the PEP details is still pending.")
    return reasons


# ── PEP (KYC-07) ───────────────────────────────────────────────────────────


def clean_pep(data: dict) -> dict:
    values = {
        "position_held": _text(data, "position_held", 200, required=True, label="Position held"),
        "country": _country(data, "country"),
        "since": parse_date(data.get("since"), "since", required=False),
        "until": parse_date(data.get("until"), "until", required=False),
        "pep_relationship": _choice(data, "pep_relationship", PEP_RELATIONSHIPS, required=True),
        "related_pep_name": _text(data, "related_pep_name", 200),
        "source_of_funds": _text(data, "source_of_funds", 2000, required=True, label="Source of funds"),
        "source_of_wealth": _text(data, "source_of_wealth", 2000, required=True, label="Source of wealth"),
    }
    if values["pep_relationship"] != "self" and not values["related_pep_name"]:
        raise ValidationError("Name the politically exposed person this client is related to.")
    if values["since"] and values["until"] and values["until"] < values["since"]:
        raise ValidationError("until can't be before since.")
    return values


def set_pep(party_id: int, data: dict, actor_user):
    """Flag a client as a PEP with the extra details (needs senior approval), or ask to clear the flag."""
    party = lock_party(party_id)
    if party.status == "merged":
        raise Conflict("This client was merged into another record.")
    if approvals_open_for(party.id, "party.pep_approve"):
        raise Conflict("A PEP change for this client is already waiting for approval.")
    if data.get("is_pep") is True:
        values = clean_pep(data)
        row = db.session.get(PartyPepDetails, party.id)
        old = row.to_dict() if row else None
        if row is None:
            row = PartyPepDetails(party_id=party.id, recorded_by=actor_user.email, status="pending", **values)
            db.session.add(row)
        else:
            for k, v in values.items():
                setattr(row, k, v)
            row.status, row.recorded_by, row.approved_at, row.approved_by = "pending", actor_user.email, None, None
        party.is_pep = True
        db.session.flush()
        create_audit_log("FLAG_PARTY_PEP", target_type="party", target_id=party.id, target_name=party.party_no,
                         old_value=old, new_value=row.to_dict())
        payload = {"party_id": party.id, "action": "approve"}
    elif data.get("is_pep") is False:
        if not party.is_pep:
            raise Conflict(f"{party.party_no} isn't flagged as a PEP.")
        payload = {"party_id": party.id, "action": "clear"}
    else:
        raise ValidationError("is_pep must be true or false.")
    cr = approvals.submit("party.pep_approve", payload, actor_user, data.get("reason"), commit=False)
    db.session.commit()
    return cr


def approvals_open_for(party_id: int, request_type: str):
    from app.Approvals.model import CR_OPEN, ChangeRequest
    return ChangeRequest.query.filter(ChangeRequest.request_type == request_type,
                                      ChangeRequest.entity_id == str(party_id),
                                      ChangeRequest.status.in_(CR_OPEN)).first()


def request_verification(party_id: int, actor_user, reason: str | None = None):
    return approvals.submit("party.verify", {"party_id": party_id}, actor_user, reason)


def find_parties_by_identifier(id_type: str, value: str):
    normalised = normalise_identifier(id_type, value)
    if not normalised:
        return None
    return (Party.query.join(PartyIdentifier, PartyIdentifier.party_id == Party.id)
            .filter(PartyIdentifier.id_type == id_type, PartyIdentifier.value_normalised == normalised).first())


def primary_contact(party_id: int, kind: str) -> str | None:
    row = (PartyContact.query.filter_by(party_id=party_id, kind=kind)
           .order_by(PartyContact.is_primary.desc(), PartyContact.id).first())
    return row.value if row else None


def count_by_status() -> dict:
    return dict(db.session.query(Party.kyc_status, func.count(Party.id)).group_by(Party.kyc_status).all())
