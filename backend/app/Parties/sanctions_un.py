"""
The UN Security Council consolidated sanctions list (FSD v0.1 KYC-06, 07 Q-CO6).

    parse(content)                     the published XML -> its date and entries
    import_xml(content, source, actor) apply it to watchlist_entries (list 'sanctions_un')
    scheduled_import(actor)            the screening.un_sanctions_import job: download and apply,
                                       when screening.un_sanctions.import_enabled is on

Each published entry (individual or entity) is one watchlist entry keyed by its
UN reference number (external_ref), with its aliases and passport / national ID
numbers, so screening matches on them like any other entry. Clients are only
screened against it while 'sanctions_un' is in screening.lists_enabled.

Re-running is safe: a file already applied (same SHA-256) changes nothing, a
file older than the last one applied is refused, and an import holds an
advisory lock so two can't interleave. An entry the UN drops is marked removed
(never deleted); if it's listed again it gets a new row. An import that would
remove more than MASS_REMOVAL_SHARE of the list is refused as a likely bad
file unless forced (flask --app main import-un-sanctions --allow-mass-removal).
"""
import hashlib
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import text

from app.database.database import db
from app.Parties.model import Party, SanctionsListImport, WatchlistEntry
from app.Parties.normalise import normalise_identifier, normalise_name
from app.Parties.screening import screen_party
from app.Settings import business
from app.utils.audit_log import create_audit_log
from app.utils.dates import utcnow
from app.utils.http import ValidationError

logger = logging.getLogger(__name__)

LIST = "sanctions_un"
SOURCE_LABEL = "UN Security Council consolidated list"
MAX_BYTES = 50 * 1024 * 1024
DOWNLOAD_TIMEOUT = (15, 300)  # connect, read (seconds)
MASS_REMOVAL_SHARE = 0.10     # refuse to delist more than this share of the active list in one import …
MASS_REMOVAL_MIN = 20         # … once it is more than this many entries
_LOCK_KEY = "sanctions_un.import"


@dataclass
class Listed:
    ref: str
    kind: str  # individual / entity
    full_name: str
    aliases: list = field(default_factory=list)
    identifiers: list = field(default_factory=list)
    details: dict = field(default_factory=dict)


@dataclass
class ParsedList:
    generated_at: datetime
    entries: list


# ── Parsing ────────────────────────────────────────────────────────────────


def _tag(el) -> str:
    return el.tag.rsplit("}", 1)[-1]


def _children(el, name):
    return [c for c in el if _tag(c) == name]


def _text(el, name) -> str:
    for c in el:
        if _tag(c) == name:
            return " ".join((c.text or "").split())
    return ""


def _values(el, name) -> list[str]:
    """<NATIONALITY><VALUE>…</VALUE><VALUE>…</VALUE></NATIONALITY> -> the values."""
    out = []
    for c in _children(el, name):
        out += [v for v in (" ".join((x.text or "").split()) for x in c if _tag(x) == "VALUE") if v]
    return out


def _id_type(document_type: str) -> str | None:
    t = document_type.lower()
    if "passport" in t:
        return "passport"
    if "national" in t and "ident" in t:
        return "national_id"
    return None


def _identifiers(el) -> list[dict]:
    out, seen = [], set()
    for doc in _children(el, "INDIVIDUAL_DOCUMENT"):
        id_type = _id_type(_text(doc, "TYPE_OF_DOCUMENT"))
        number = re.sub(r"\(.*?\)", " ", _text(doc, "NUMBER")).strip()
        value = normalise_identifier(id_type, number) if id_type else None
        if not value or len(value) > 50 or (id_type, value) in seen:
            continue
        seen.add((id_type, value))
        out.append({"id_type": id_type, "value": number[:50], "value_normalised": value,
                    "issuing_country": _text(doc, "ISSUING_COUNTRY") or _text(doc, "COUNTRY_OF_ISSUE") or None})
    return out


def _aliases(el, tag: str, full_name_normalised: str) -> list[dict]:
    out, seen = [], {full_name_normalised}
    for a in _children(el, tag):
        name = _text(a, "ALIAS_NAME")[:200]
        normalised = normalise_name(name)
        if not normalised or normalised in seen:
            continue
        seen.add(normalised)
        out.append({"name": name, "name_normalised": normalised, "quality": _text(a, "QUALITY") or None})
    return out


def _dates_of_birth(el) -> list[str]:
    out = []
    for d in _children(el, "INDIVIDUAL_DATE_OF_BIRTH"):
        value = _text(d, "DATE") or _text(d, "YEAR")
        if not value and _text(d, "FROM_YEAR"):
            value = f"{_text(d, 'FROM_YEAR')}–{_text(d, 'TO_YEAR')}"
        if value:
            out.append(value)
    return out


def _entry(el, kind: str) -> Listed | None:
    ref = _text(el, "REFERENCE_NUMBER")
    if kind == "individual":
        full_name = " ".join(p for p in (_text(el, n) for n in ("FIRST_NAME", "SECOND_NAME", "THIRD_NAME",
                                                                  "FOURTH_NAME")) if p)
    else:
        full_name = _text(el, "FIRST_NAME")
    full_name = full_name[:200]
    if not ref or not normalise_name(full_name):
        logger.warning("Skipping a UN list %s without a reference number or name (DATAID %s)",
                       kind, _text(el, "DATAID"))
        return None
    details = {
        "kind": kind,
        "dataid": _text(el, "DATAID") or None,
        "version": _text(el, "VERSIONNUM") or None,
        "un_list_type": _text(el, "UN_LIST_TYPE") or None,
        "listed_on": _text(el, "LISTED_ON") or None,
        "last_updated": _values(el, "LAST_DAY_UPDATED"),
        "name_original_script": _text(el, "NAME_ORIGINAL_SCRIPT") or None,
        "comments": _text(el, "COMMENTS1")[:2000] or None,
    }
    if kind == "individual":
        details |= {"nationality": _values(el, "NATIONALITY"), "date_of_birth": _dates_of_birth(el),
                    "designation": _values(el, "DESIGNATION")}
    alias_tag = "INDIVIDUAL_ALIAS" if kind == "individual" else "ENTITY_ALIAS"
    return Listed(ref=ref[:40], kind=kind, full_name=full_name,
                  aliases=_aliases(el, alias_tag, normalise_name(full_name)),
                  identifiers=_identifiers(el) if kind == "individual" else [], details=details)


def _generated_at(root) -> datetime:
    raw = (root.get("dateGenerated") or "").strip()
    try:
        when = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        raise ValidationError("The UN list has no readable dateGenerated, so its version can't be recorded.")
    return when if when.tzinfo else when.replace(tzinfo=timezone.utc)


def parse(content: bytes) -> ParsedList:
    head = content[:4096].upper()
    if b"<!DOCTYPE" in head or b"<!ENTITY" in head:
        raise ValidationError("The UN list file declares a DTD or entities; refusing to parse it.")
    try:
        root = ET.fromstring(content)
    except ET.ParseError as e:
        raise ValidationError(f"The UN list file isn't valid XML ({e}).")
    if _tag(root) != "CONSOLIDATED_LIST":
        raise ValidationError("This isn't the UN consolidated list (no CONSOLIDATED_LIST root).")
    entries, refs = [], set()
    for group, item, kind in (("INDIVIDUALS", "INDIVIDUAL", "individual"), ("ENTITIES", "ENTITY", "entity")):
        for g in _children(root, group):
            for el in _children(g, item):
                entry = _entry(el, kind)
                if entry is None:
                    continue
                if entry.ref in refs:
                    logger.warning("UN list reference %s appears twice; keeping the first", entry.ref)
                    continue
                refs.add(entry.ref)
                entries.append(entry)
    if not entries:
        raise ValidationError("The UN list file has no entries; refusing to delist everyone.")
    return ParsedList(generated_at=_generated_at(root), entries=entries)


# ── Applying ───────────────────────────────────────────────────────────────


def _fields(item: Listed) -> dict:
    listed = item.details.get("listed_on")
    reason = (f"UN Security Council sanctions ({item.details.get('un_list_type') or 'consolidated list'}), "
              f"reference {item.ref}" + (f", listed {listed}" if listed else "") + ".")
    return {"full_name": item.full_name, "name_normalised": normalise_name(item.full_name)[:200],
            "aliases": item.aliases, "identifiers": item.identifiers, "details": item.details, "reason": reason}


def latest_import() -> SanctionsListImport | None:
    return (SanctionsListImport.query.filter_by(list=LIST)
            .order_by(SanctionsListImport.list_generated_at.desc(), SanctionsListImport.id.desc()).first())


def import_xml(content: bytes, source: str, actor: str, *, allow_mass_removal: bool = False) -> dict:
    """Apply a downloaded copy of the list, screen clients against what changed, and commit."""
    parsed = parse(content)
    sha = hashlib.sha256(content).hexdigest()
    db.session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": _LOCK_KEY})
    done = SanctionsListImport.query.filter_by(list=LIST, content_sha256=sha).first()
    if done is not None:
        db.session.commit()  # releases the lock
        return {"status": "unchanged", "import_id": done.id, "list_generated_at": done.list_generated_at.isoformat()}
    last = latest_import()
    if last is not None and parsed.generated_at < last.list_generated_at:
        raise ValidationError(f"This copy of the UN list ({parsed.generated_at.isoformat()}) is older than the one "
                              f"already imported ({last.list_generated_at.isoformat()}).")

    active = {e.external_ref: e for e in WatchlistEntry.query.filter(
        WatchlistEntry.list == LIST, WatchlistEntry.status == "active",
        WatchlistEntry.external_ref.isnot(None)).with_for_update()}
    to_add, to_update = [], []
    for item in parsed.entries:
        fields = _fields(item)
        entry = active.get(item.ref)
        if entry is None:
            to_add.append((item, fields))
        elif any(getattr(entry, k) != v for k, v in fields.items()):
            to_update.append((entry, fields))
    listed = {item.ref for item in parsed.entries}
    to_remove = [e for ref, e in sorted(active.items()) if ref not in listed]
    if (not allow_mass_removal and len(to_remove) > MASS_REMOVAL_MIN
            and len(to_remove) > MASS_REMOVAL_SHARE * len(active)):
        raise ValidationError(f"This copy of the UN list would remove {len(to_remove)} of {len(active)} entries. "
                              "Check the file; if it's right, import it with --allow-mass-removal.")

    now = utcnow()
    record = SanctionsListImport(list=LIST, source=source[:500], list_generated_at=parsed.generated_at,
                                 content_sha256=sha, entries_in_list=len(parsed.entries), added=len(to_add),
                                 updated=len(to_update), removed=len(to_remove), imported_by=actor, imported_at=now)
    db.session.add(record)
    db.session.flush()
    changed = []
    for item, fields in to_add:
        entry = WatchlistEntry(list=LIST, external_ref=item.ref, source=SOURCE_LABEL, status="active",
                               added_by=actor, added_at=now, import_id=record.id, **fields)
        db.session.add(entry)
        changed.append(entry)
    for entry, fields in to_update:
        for k, v in fields.items():
            setattr(entry, k, v)
        entry.import_id = record.id
        changed.append(entry)
    for entry in to_remove:
        entry.status, entry.removed_by, entry.removed_at, entry.import_id = "removed", actor, now, record.id
    db.session.flush()
    create_audit_log("IMPORT_SANCTIONS_LIST", target_type="sanctions_list_import", target_id=record.id,
                     target_name=f"UN list {parsed.generated_at.date().isoformat()}",
                     description=f"Imported the {SOURCE_LABEL} of {parsed.generated_at.isoformat()}: "
                                 f"{len(to_add)} added, {len(to_update)} updated, {len(to_remove)} removed.",
                     new_value={**record.to_dict(), "added_refs": [i.ref for i, _ in to_add],
                                "updated_refs": [e.external_ref for e, _ in to_update],
                                "removed_refs": [e.external_ref for e in to_remove]},
                     actor_user_email=actor)
    matched = 0
    if changed:
        for party in Party.query.filter(Party.status == "active").order_by(Party.id).all():
            if screen_party(party, "watchlist_change", actor, entries=changed) is not None:
                matched += 1
    db.session.commit()
    return {"status": "applied", **record.to_dict(), "matched_parties": matched}


def download(url: str) -> bytes:
    import requests

    with requests.get(url, timeout=DOWNLOAD_TIMEOUT, stream=True) as res:
        res.raise_for_status()
        buf = bytearray()
        for chunk in res.iter_content(1 << 16):
            buf += chunk
            if len(buf) > MAX_BYTES:
                raise ValidationError(f"The UN list download is larger than {MAX_BYTES // (1024 * 1024)} MB.")
    return bytes(buf)


def scheduled_import(actor: str = "scheduler") -> dict:
    if not business.get("screening.un_sanctions.import_enabled"):
        return {"status": "disabled"}
    url = business.get("screening.un_sanctions.source_url")
    return import_xml(download(url), url, actor)
