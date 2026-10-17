"""
Cross-document checks, in code (AI-06; 05 §7.0). They read only APPROVED reviews
(confirmed values), never raw AI output.

Each check → {check, status: pass | fail | needs_review | missing | not_applicable,
              reason, evidence: [{source, value, page}]}

    name_consistent         applicant's name on the ID / passport, the KRA PIN certificate
                            and the application (the client record). Compared after
                            upper-casing, removing punctuation and titles and sorting words,
                            so case, spacing and name order don't matter. The same words →
                            pass; close but not the same (similarity ≥ 0.90, or a missing
                            middle name) → needs_review, never pass; otherwise fail.
    id_number_consistent    ID / passport number on the document and the record, and the
                            KRA PIN on the certificate and the record: equal → pass, else fail
    cr12_directors_match    organisations: CR12 directors against the directors captured on
                            the client (by ID number, else name); lists missing and extra
    collateral_owner_match  logbook / title-deed owners are the applicant or a guarantor; a
                            financier interest or an encumbrance → needs_review
"""
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from app.Applications import review as reviews
from app.Applications import service as applications
from app.database.database import db
from app.DocAI.model import ExtractedField, Extraction
from app.Parties.model import Party, PartyIdentifier, PartyRelationship
from app.Parties.normalise import normalise_identifier, normalise_name

FUZZY = 0.90
TITLES = {"MR", "MRS", "MS", "MISS", "DR", "PROF", "ENG", "HON", "REV", "SIR", "MADAM"}
PASS, FAIL, REVIEW, MISSING, NA = "pass", "fail", "needs_review", "missing", "not_applicable"
COLLATERAL_PRODUCTS = ("business_loan", "asset_finance")


def name_key(value: str | None) -> str:
    words = [w for w in normalise_name(value).split() if w not in TITLES]
    return " ".join(sorted(words))


def compare_names(a: str | None, b: str | None) -> str:
    """pass when the same words; needs_review when close (fuzzy or a missing middle name); else fail."""
    ka, kb = name_key(a), name_key(b)
    if not ka or not kb:
        return MISSING
    if ka == kb:
        return PASS
    wa, wb = set(ka.split()), set(kb.split())
    if (wa < wb or wb < wa) and len(wa & wb) >= 2:
        return REVIEW
    return REVIEW if SequenceMatcher(None, ka, kb).ratio() >= FUZZY else FAIL


@dataclass
class Source:
    """The confirmed values of one approved reading."""
    extraction: Extraction
    values: dict
    pages: dict = field(default_factory=dict)

    @property
    def doc_type(self):
        return self.extraction.declared_type

    def ev(self, path: str, label: str | None = None) -> dict:
        return {"source": label or f"{self.doc_type} (reading {self.extraction.id})", "field": path,
                "value": self.values.get(path), "page": self.pages.get(path)}


def confirmed_sources(application_id: int) -> list[Source]:
    out = []
    for ex in applications.latest_extractions(application_id):
        review = reviews.approved_review_for(ex)
        if review is None:
            continue
        pages = {f.field_path: f.source_page for f in ExtractedField.query.filter_by(extraction_id=ex.id)}
        out.append(Source(ex, reviews.confirmed_values(ex, review), pages))
    return out


def _of(sources, doc_type, party_id=None):
    return [s for s in sources if s.doc_type == doc_type and (party_id is None or s.extraction.party_id == party_id)]


def _result(check, status, reason, evidence=()):
    return {"check": check, "status": status, "reason": reason, "evidence": list(evidence)}


def _sentence(text: str) -> str:
    return text[:1].upper() + text[1:] + "."


def _worst(statuses: list[str]) -> str:
    for s in (FAIL, REVIEW, MISSING):
        if s in statuses:
            return s
    return PASS if statuses else MISSING


def check_names(party: Party, sources: list[Source]) -> dict:
    record = {"source": "application (client record)", "field": "name", "value": party.display_name, "page": None}
    names = []
    if party.party_type == "person":
        for s in _of(sources, "national_id", party.id):
            names.append(s.ev("full_name", "National ID"))
        for s in _of(sources, "passport", party.id):
            names.append({**s.ev("given_names", "Passport"),
                          "value": " ".join(v for v in (s.values.get("given_names"), s.values.get("surname")) if v)
                          or None})
        for s in _of(sources, "kra_pin", party.id):
            names.append(s.ev("taxpayer_name", "KRA PIN certificate"))
    else:
        for doc_type, path, label in (("certificate_of_incorporation", "entity_name", "Certificate of incorporation"),
                                      ("cr12", "company_name", "CR12"), ("kra_pin", "taxpayer_name",
                                                                         "KRA PIN certificate")):
            for s in _of(sources, doc_type, party.id):
                names.append(s.ev(path, label))
    names = [n for n in names if n["value"]]
    if not names:
        return _result("name_consistent", MISSING, "No approved identity document to compare the name with.",
                       [record])
    statuses = [compare_names(record["value"], n["value"]) for n in names]
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            statuses.append(compare_names(a["value"], b["value"]))
    status = _worst(statuses)
    reason = {PASS: "The name is the same on every document and the record.",
              REVIEW: "The names are close but not the same (order, spelling or a missing name): check them.",
              FAIL: "The names don't match."}.get(status, "Not enough names to compare.")
    return _result("name_consistent", status, reason, [record, *names])


def _identifier(party_id: int, id_type: str) -> str | None:
    row = PartyIdentifier.query.filter_by(party_id=party_id, id_type=id_type).first()
    return row.value_display if row else None


def check_ids(party: Party, sources: list[Source]) -> dict:
    pairs = []  # (document evidence, record evidence, id_type)
    if party.party_type == "person":
        for doc_type, path, id_type, label in (("national_id", "id_number", "national_id", "National ID"),
                                               ("passport", "passport_number", "passport", "Passport")):
            for s in _of(sources, doc_type, party.id):
                pairs.append((s.ev(path, label), id_type))
    for s in _of(sources, "kra_pin", party.id):
        pairs.append((s.ev("kra_pin", "KRA PIN certificate"), "kra_pin"))
    for doc_type, label in (("certificate_of_incorporation", "Certificate of incorporation"), ("cr12", "CR12")):
        for s in _of(sources, doc_type, party.id):
            pairs.append((s.ev("registration_number", label), "company_reg_no"))
    pairs = [(e, t) for e, t in pairs if e["value"]]
    if not pairs:
        return _result("id_number_consistent", MISSING, "No approved document with an ID number or PIN.")
    evidence, statuses, problems = [], [], []
    for e, id_type in pairs:
        recorded = _identifier(party.id, id_type)
        record = {"source": "application (client record)", "field": id_type, "value": recorded, "page": None}
        evidence += [e, record]
        if recorded is None:
            statuses.append(MISSING)
            problems.append(f"the record has no {id_type.replace('_', ' ')}")
        elif normalise_identifier(id_type, recorded) == normalise_identifier(id_type, e["value"]):
            statuses.append(PASS)
        else:
            statuses.append(FAIL)
            problems.append(f"{e['source']} shows {e['value']}, the record {recorded}")
    status = _worst(statuses)
    reason = "Every ID number and PIN matches the record." if status == PASS else \
        _sentence("; ".join(problems))
    return _result("id_number_consistent", status, reason, evidence)


def _person_ids(party_id: int) -> set[str]:
    return {normalise_identifier(r.id_type, r.value_display) for r in
            PartyIdentifier.query.filter(PartyIdentifier.party_id == party_id,
                                         PartyIdentifier.id_type.in_(("national_id", "passport", "alien_id")))}


def check_directors(party: Party, sources: list[Source]) -> dict:
    if party.party_type != "organisation":
        return _result("cr12_directors_match", NA, "The applicant is an individual.")
    cr12 = _of(sources, "cr12", party.id)
    if not cr12:
        return _result("cr12_directors_match", MISSING, "No approved CR12.")
    s = cr12[0]
    listed = []
    i = 0
    while f"directors[{i}].name" in s.values:
        listed.append({"name": s.values.get(f"directors[{i}].name"),
                       "id": s.values.get(f"directors[{i}].id_or_passport_number"), "page": s.pages.get(
                           f"directors[{i}].name")})
        i += 1
    captured = []
    for rel in PartyRelationship.query.filter_by(to_party_id=party.id, relationship="director", status="active"):
        person = db.session.get(Party, rel.from_party_id)
        captured.append({"name": person.display_name, "ids": _person_ids(person.id), "party_no": person.party_no})
    unmatched = list(captured)
    missing, close = [], []
    for d in listed:
        hit = None
        if d["id"]:
            ids = {normalise_identifier("national_id", d["id"]), normalise_identifier("passport", d["id"])}
            hit = next((c for c in unmatched if c["ids"] & ids), None)
        if hit is None:
            hit = next((c for c in unmatched if compare_names(c["name"], d["name"]) == PASS), None)
        if hit is None:
            near = next((c for c in unmatched if compare_names(c["name"], d["name"]) == REVIEW), None)
            if near is not None:
                close.append(f"{d['name']} ~ {near['name']}")
                unmatched.remove(near)
                continue
            missing.append(d["name"])
        else:
            unmatched.remove(hit)
    extra = [c["name"] for c in unmatched]
    evidence = [{"source": "CR12", "field": "directors", "value": d["name"], "id": d["id"], "page": d["page"]}
                for d in listed] + [{"source": "captured director", "field": c["party_no"], "value": c["name"],
                                     "page": None} for c in captured]
    if missing or extra:
        parts = []
        if missing:
            parts.append("On the CR12 but not captured: " + ", ".join(missing))
        if extra:
            parts.append("Captured but not on the CR12: " + ", ".join(extra))
        return _result("cr12_directors_match", FAIL, ". ".join(parts) + ".", evidence)
    if close:
        return _result("cr12_directors_match", REVIEW, "Names close but not the same: " + "; ".join(close) + ".",
                       evidence)
    return _result("cr12_directors_match", PASS, f"All {len(listed)} CR12 director(s) are captured.", evidence)


def _owners(text: str | None) -> list[str]:
    return [p.strip() for p in re.split(r"[;\n]| AND |&", text or "", flags=re.I) if p.strip()]


def check_collateral(app, party: Party, sources: list[Source]) -> dict:
    owners_ok = [party] + [db.session.get(Party, pid) for pid in applications.guarantor_ids(app.id)]
    docs = [(s, "registered_owners", "financier_interest", "Logbook") for s in _of(sources, "logbook")]
    docs += [(s, "registered_proprietors", "encumbrances", "Title deed") for s in _of(sources, "title_deed")]
    if not docs:
        if app.product_code in COLLATERAL_PRODUCTS:
            return _result("collateral_owner_match", MISSING, "No approved logbook or title deed.")
        return _result("collateral_owner_match", NA, "This product has no collateral (WA-04).")
    statuses, evidence, problems = [], [], []
    for s, owner_path, interest_path, label in docs:
        evidence.append(s.ev(owner_path, label))
        for owner in _owners(s.values.get(owner_path)):
            best = FAIL
            for p in owners_ok:
                got = compare_names(p.display_name, owner)
                best = PASS if got == PASS else (REVIEW if got == REVIEW and best != PASS else best)
            statuses.append(best)
            if best == FAIL:
                problems.append(f"{label} owner {owner} is neither the applicant nor a guarantor")
            elif best == REVIEW:
                problems.append(f"{label} owner {owner} is close to, but not the same as, the applicant or a "
                                "guarantor")
        interest = s.values.get(interest_path)
        if interest:
            evidence.append(s.ev(interest_path, label))
            statuses.append(REVIEW)
            problems.append(f"{label} shows {interest_path.replace('_', ' ')}: {interest}")
    if not statuses:
        return _result("collateral_owner_match", MISSING, "No owner was confirmed on the collateral documents.",
                       evidence)
    status = _worst(statuses)
    reason = "Every collateral owner is the applicant or a guarantor." if status == PASS else \
        "; ".join(problems) + "."
    return _result("collateral_owner_match", status, reason, evidence)


def run(application_id: int) -> list[dict]:
    app = applications.get(application_id)
    party = db.session.get(Party, app.party_id)
    sources = confirmed_sources(app.id)
    return [check_names(party, sources), check_ids(party, sources), check_directors(party, sources),
            check_collateral(app, party, sources)]

