"""
The investment role of a party (02-domain-model §1.3, §6).

An investor row is the party's investment account: its ACL- client code is the
account number, its email is the statement address (one investor per email,
unchanged), and its name, phone, ID, PIN and payout columns mirror the party so
statements, emails and reports read exactly what they read before. The party
is the source of truth; every write goes through here so both stay in step.
"""
from app.Branches.model import HEAD_OFFICE_ID
from app.database.database import db
from app.Parties import service as parties
from app.Parties.model import Account, Party, PartyBankAccount, PartyContact, PartyIdentifier, PartyPerson
from app.Parties.normalise import normalise_email, normalise_identifier, normalise_phone
from app.Parties.preflight import classify_id
from app.utils.dates import today_eat
from app.utils.http import Conflict, ValidationError

PERSON_DOCS = ("national_id", "passport", "alien_id")


def split_name(full_name: str) -> dict:
    words = full_name.split()
    if len(words) == 1:
        return {"first_name": None, "middle_name": None, "last_name": words[0]}
    if len(words) == 2:
        return {"first_name": words[0], "middle_name": None, "last_name": words[1]}
    return {"first_name": words[0], "middle_name": " ".join(words[1:-1]), "last_name": words[-1]}


def _identifiers(values: dict) -> list[dict]:
    out = []
    if values.get("id_number"):
        out.append({"id_type": classify_id(values["id_number"]), "issuing_country": "KE",
                    "value_display": values["id_number"],
                    "value_normalised": normalise_identifier("national_id", values["id_number"]),
                    "issued_on": None, "expires_on": None})
    if values.get("kra_pin"):
        out.append({"id_type": "kra_pin", "issuing_country": "KE", "value_display": values["kra_pin"],
                    "value_normalised": normalise_identifier("kra_pin", values["kra_pin"]),
                    "issued_on": None, "expires_on": None})
    return [i for i in out if i["value_normalised"]]


def _bank(values: dict) -> list[dict]:
    if not values.get("payout_account"):
        return []
    kind = values.get("payout_method") or ("bank" if values.get("bank_name") else "mpesa")
    return [{"kind": kind, "bank_name": values.get("bank_name"), "branch_name": None,
             "account_no": values["payout_account"], "account_name": None, "is_default_payout": True}]


def _assert_free(identifiers: list[dict], exclude_party_id: int | None = None) -> None:
    try:
        parties.assert_identifiers_free(identifiers, exclude_party_id)
    except Conflict as e:
        raise Conflict(f"{e.message} Open that client and add the investment account there, so one person "
                       f"keeps one record.")


def new_party_for_investor(values: dict, actor: str, branch_id: int = HEAD_OFFICE_ID) -> Party:
    """A person party from the investor form's fields (identifiers checked for duplicates)."""
    identifiers = _identifiers(values)
    _assert_free(identifiers)
    contacts = [{"kind": "email", "value": values["email"], "value_normalised": normalise_email(values["email"]),
                 "is_primary": True}]
    if values.get("phone"):
        contacts.append({"kind": "mobile", "value": values["phone"], "value_normalised": normalise_phone(values["phone"]),
                         "is_primary": True})
    person = {**split_name(values["full_name"]), "name_needs_review": True}
    party = parties.insert_party(party_type="person", person=person, organisation=None, identifiers=identifiers,
                                 contacts=contacts, addresses=[], bank_accounts=_bank(values), actor=actor,
                                 home_branch_id=branch_id, display_name=values["full_name"])
    return party


def open_investment_account(party: Party, client_code: str, actor: str, branch_id: int) -> Account:
    if db.session.query(Account.id).filter(Account.party_id == party.id, Account.account_type == "investment").first():
        raise Conflict(f"{party.party_no} already has an investment account.")
    account = Account(account_no=client_code, account_type="investment", party_id=party.id, branch_id=branch_id,
                      status="active", opened_on=today_eat(), created_by=actor)
    db.session.add(account)
    parties.add_role(party, "investor", branch_id)
    db.session.flush()
    return account


def investor_fields_from_party(party: Party) -> dict:
    """What the investor's mirrored columns hold for this party."""
    ident = {i.id_type: i.value_display for i in PartyIdentifier.query.filter_by(party_id=party.id)}
    bank = (PartyBankAccount.query.filter_by(party_id=party.id, status="active", is_default_payout=True).first())
    return {
        "full_name": party.display_name,
        "phone": parties.primary_contact(party.id, "mobile") or parties.primary_contact(party.id, "phone"),
        "id_number": next((ident[t] for t in PERSON_DOCS if t in ident), None),
        "kra_pin": ident.get("kra_pin"),
        "payout_method": bank.kind if bank else None,
        "bank_name": bank.bank_name if bank else None,
        "payout_account": bank.account_no if bank else None,
    }


def _set_contact(party: Party, kind: str, value: str | None) -> None:
    row = (PartyContact.query.filter_by(party_id=party.id, kind=kind)
           .order_by(PartyContact.is_primary.desc(), PartyContact.id).first())
    if value is None:
        if row is not None:
            db.session.delete(row)
        return
    normalised = normalise_email(value) if kind == "email" else normalise_phone(value)
    if row is None:
        db.session.add(PartyContact(party_id=party.id, kind=kind, value=value, value_normalised=normalised,
                                    is_primary=True))
    else:
        row.value, row.value_normalised = value, normalised


def _set_identifier(party: Party, types: tuple[str, ...], new: dict | None) -> None:
    rows = PartyIdentifier.query.filter(PartyIdentifier.party_id == party.id, PartyIdentifier.id_type.in_(types)).all()
    if new is None:
        for row in rows:
            db.session.delete(row)
        return
    keep = next((r for r in rows if r.id_type == new["id_type"]), None)
    for row in rows:
        if row is not keep:
            db.session.delete(row)
    db.session.flush()
    if keep is None:
        db.session.add(PartyIdentifier(party_id=party.id, **new))
    else:
        keep.value_display, keep.value_normalised = new["value_display"], new["value_normalised"]


def _set_payout(party: Party, values: dict) -> None:
    current = PartyBankAccount.query.filter_by(party_id=party.id, status="active", is_default_payout=True).first()
    wanted = _bank(values)
    if current is not None and wanted and (current.kind, current.bank_name, current.account_no) == (
            wanted[0]["kind"], wanted[0]["bank_name"], wanted[0]["account_no"]):
        return
    if current is not None:
        current.status = "ended"  # kept for the record, never deleted
        db.session.flush()
    if wanted:
        db.session.add(PartyBankAccount(party_id=party.id, status="active", **wanted[0]))


def apply_investor_fields(party: Party, values: dict) -> None:
    """Write investor-form fields (any subset) onto the party."""
    if "full_name" in values:
        party.display_name = values["full_name"]
        person = db.session.get(PartyPerson, party.id)
        if person is not None:
            for k, v in split_name(values["full_name"]).items():
                setattr(person, k, v)
            person.name_needs_review = True
    if "email" in values:
        _set_contact(party, "email", values["email"])
    if "phone" in values:
        _set_contact(party, "mobile", values["phone"])
    if "id_number" in values or "kra_pin" in values:
        idents = {i["id_type"]: i for i in _identifiers(values)}
        _assert_free(list(idents.values()), exclude_party_id=party.id)
        if "id_number" in values:
            new = next((idents[t] for t in PERSON_DOCS if t in idents), None)
            _set_identifier(party, PERSON_DOCS, new)
        if "kra_pin" in values:
            _set_identifier(party, ("kra_pin",), idents.get("kra_pin"))
    if {"payout_method", "bank_name", "payout_account"} & set(values):
        from app.Investors.model import Investor
        investor = Investor.query.filter_by(party_id=party.id).first()
        merged = {k: getattr(investor, k) for k in ("payout_method", "bank_name", "payout_account")} if investor else {}
        merged.update({k: values[k] for k in ("payout_method", "bank_name", "payout_account") if k in values})
        _set_payout(party, merged)
    db.session.flush()
    parties.refresh_kyc_status(party)


def statement_email_for(party: Party, requested: str | None) -> str:
    email = normalise_email(requested) or normalise_email(parties.primary_contact(party.id, "email"))
    if not email:
        raise ValidationError("A statement email is required for an investment account.")
    return email
