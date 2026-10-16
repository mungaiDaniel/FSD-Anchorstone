"""
Screening parties against Anchorstone's watchlists (FSD v0.1 KYC-06).

    screen_party(party, trigger, actor)   on onboarding, identity changes and
                                          watchlist additions; daily for everyone
                                          (screening.rescreen job)
    review(result_id, decision, note)     a reviewer clears or confirms a match

A party matches an active entry on an enabled list (setting
screening.lists_enabled) when an identifier is the same after normalising, or
the normalised names are equal (an entry's aliases count as its names). The UN
sanctions list is loaded by app/Parties/sanctions_un.py. A potential match blocks KYC verification until
it's reviewed. The reviewer can't be the person who onboarded the party: the
service checks it (assert_can_decide) and a CHECK constraint backs it up.
A confirmed blacklist match makes the party `blacklisted`; a confirmed PEP-list
match flags the party as a PEP (KYC-07 then asks for the extra details).
"""
from app.Approvals.policy import assert_can_decide
from app.database.database import db
from app.Parties.model import (
    WATCHLISTS,
    Party,
    PartyIdentifier,
    PartyOrganisation,
    ScreeningResult,
    WatchlistEntry,
)
from app.Parties.normalise import ID_TYPES, normalise_identifier, normalise_name
from app.Settings import business
from app.utils.audit_log import create_audit_log
from app.utils.dates import utcnow
from app.utils.http import Conflict, NotFound, ValidationError

MAKER_MESSAGE = "Maker-checker: you onboarded this client, so another person must review the screening match."


def _party_names(party: Party) -> set[str]:
    names = {normalise_name(party.display_name)}
    org = db.session.get(PartyOrganisation, party.id)
    if org is not None:
        names |= {normalise_name(org.legal_name), normalise_name(org.trading_name)}
    return {n for n in names if n}


def matches_for(party: Party, entries=None) -> list[dict]:
    lists = business.get("screening.lists_enabled")
    if entries is None:
        entries = WatchlistEntry.query.filter(WatchlistEntry.status == "active", WatchlistEntry.list.in_(lists)).all()
    else:
        entries = [e for e in entries if e.status == "active" and e.list in lists]
    if not entries:
        return []
    names = _party_names(party)
    idents = {(i.id_type, i.value_normalised) for i in PartyIdentifier.query.filter_by(party_id=party.id)}
    out = []
    for e in entries:
        on, label = [], e.full_name
        if e.name_normalised in names:
            on.append("name")
        else:
            alias = next((a for a in (e.aliases or []) if a.get("name_normalised") in names), None)
            if alias is not None:
                on.append("name")
                label = f"{e.full_name} (alias {alias.get('name')})"
        if any((i.get("id_type"), i.get("value_normalised")) in idents for i in (e.identifiers or [])):
            on.append("identifier")
        if on:
            out.append({"entry_id": e.id, "list": e.list, "name": label, "matched_on": on})
    return sorted(out, key=lambda m: m["entry_id"])


def latest(party_id: int) -> ScreeningResult | None:
    return (ScreeningResult.query.filter_by(party_id=party_id)
            .order_by(ScreeningResult.screened_at.desc(), ScreeningResult.id.desc()).first())


def screen_party(party: Party, trigger: str, actor: str, entries=None, *, record_if_unchanged: bool = True):
    """Screen and record the result (no commit). Returns the new row, or None when nothing changed and
    record_if_unchanged is False (the daily re-screen only writes what's new)."""
    found = matches_for(party, entries)
    if entries is not None:  # screening against new entries only: keep any earlier open matches
        if not found:
            return None
    previous = latest(party.id)
    if not record_if_unchanged and previous is not None:
        if [m["entry_id"] for m in previous.matches] == [m["entry_id"] for m in found]:
            return None
    # An entry already reviewed for this party isn't raised again.
    reviewed = {m["entry_id"] for r in ScreeningResult.query.filter(
        ScreeningResult.party_id == party.id, ScreeningResult.review_status.in_(("cleared", "confirmed")))
        for m in r.matches}
    open_ = [m for m in found if m["entry_id"] not in reviewed]
    if not record_if_unchanged and not open_ and previous is not None and previous.outcome == "clear":
        return None
    row = ScreeningResult(party_id=party.id, trigger=trigger, lists=business.get("screening.lists_enabled"),
                          matches=open_, outcome="potential_match" if open_ else "clear",
                          review_status="pending" if open_ else "not_required", maker_email=party.created_by,
                          screened_by=actor, screened_at=utcnow())
    db.session.add(row)
    db.session.flush()
    if open_:
        create_audit_log("SCREENING_MATCH", target_type="party", target_id=party.id, target_name=party.party_no,
                         description=f"Possible watchlist match for {party.display_name}: "
                                     + ", ".join(f"{m['name']} ({m['list']})" for m in open_),
                         new_value=row.to_dict(), actor_user_email=actor if actor == "scheduler" else None)
    return row


def pending_for(party_id: int) -> list[ScreeningResult]:
    return ScreeningResult.query.filter_by(party_id=party_id, review_status="pending").all()


def review(result_id: int, data: dict, actor_email: str) -> ScreeningResult:
    decision = str(data.get("decision") or "").strip().lower()
    if decision not in ("clear", "confirmed"):
        raise ValidationError("decision must be clear or confirmed.")
    note = str(data.get("note") or "").strip()
    if not note:
        raise ValidationError("A note is required: say why the match is or isn't the same person.")
    row = (db.session.query(ScreeningResult).filter(ScreeningResult.id == result_id).with_for_update().one_or_none())
    if row is None:
        raise NotFound("Screening result not found.")
    if row.review_status != "pending":
        raise Conflict(f"This screening result is already {row.review_status}.")
    party = db.session.query(Party).filter(Party.id == row.party_id).with_for_update().one()
    assert_can_decide("screening.review", maker_email=row.maker_email, actor_email=actor_email, amount=None,
                      branch_id=party.home_branch_id, maker_message=MAKER_MESSAGE)
    row.review_status = "cleared" if decision == "clear" else "confirmed"
    row.reviewed_by, row.reviewed_at, row.review_note = actor_email, utcnow(), note[:2000]
    old_status, old_pep = party.status, party.is_pep
    if decision == "confirmed":
        lists = {m["list"] for m in row.matches}
        if "internal_blacklist" in lists or "sanctions_un" in lists:
            party.status = "blacklisted"
        if "pep" in lists:
            party.is_pep = True
    create_audit_log("REVIEW_SCREENING_MATCH", target_type="party", target_id=party.id, target_name=party.party_no,
                     description=f"Screening match {row.review_status}: {note}",
                     old_value={"review_status": "pending", "status": old_status, "is_pep": old_pep},
                     new_value={"review_status": row.review_status, "status": party.status, "is_pep": party.is_pep})
    db.session.commit()
    return row


# ── Watchlist ──────────────────────────────────────────────────────────────


def add_entry(data: dict, actor: str) -> tuple[WatchlistEntry, int]:
    """Add a name to a list (audited) and screen every party against it. Returns (entry, matches found)."""
    list_ = str(data.get("list") or "").strip()
    if list_ not in WATCHLISTS:
        raise ValidationError(f"list must be one of: {', '.join(WATCHLISTS)}.")
    name = str(data.get("full_name") or "").strip()
    if not name or len(name) > 200:
        raise ValidationError("full_name is required (at most 200 characters).")
    reason = str(data.get("reason") or "").strip()
    if not reason:
        raise ValidationError("A reason is required.")
    identifiers = []
    for i in data.get("identifiers") or []:
        id_type = str((i or {}).get("id_type") or "")
        if id_type not in ID_TYPES:
            raise ValidationError(f"identifier id_type must be one of: {', '.join(ID_TYPES)}.")
        value = normalise_identifier(id_type, (i or {}).get("value"))
        if value:
            identifiers.append({"id_type": id_type, "value": str(i.get("value")).strip(), "value_normalised": value})
    entry = WatchlistEntry(list=list_, full_name=name, name_normalised=normalise_name(name), identifiers=identifiers,
                           reason=reason[:2000], source=(str(data.get("source") or "").strip() or None),
                           status="active", added_by=actor, added_at=utcnow())
    db.session.add(entry)
    db.session.flush()
    create_audit_log("ADD_WATCHLIST_ENTRY", target_type="watchlist_entry", target_id=entry.id, target_name=name,
                     new_value=entry.to_dict())
    found = 0
    for party in Party.query.filter(Party.status == "active").all():
        if screen_party(party, "watchlist_change", actor, entries=[entry]) is not None:
            found += 1
    db.session.commit()
    return entry, found


def rescreen_all(actor: str = "scheduler") -> dict:
    """The daily screening of existing parties. Idempotent: only changes are recorded."""
    screened = recorded = 0
    for party in Party.query.filter(Party.status == "active").order_by(Party.id).all():
        screened += 1
        if screen_party(party, "rescreen", actor, record_if_unchanged=False) is not None:
            recorded += 1
    db.session.commit()
    return {"screened": screened, "recorded": recorded}
