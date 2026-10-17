"""UN Security Council consolidated sanctions list import (FSD v0.1 KYC-06, 07 Q-CO6). Never downloads."""
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.database.database import db
from app.Jobs.registry import PERIODIC_BY_NAME, TASKS
from app.Parties import sanctions_un
from app.Parties.model import Party, SanctionsListImport, ScreeningResult, WatchlistEntry
from app.Settings import business
from app.Settings.registry import normalise
from app.utils.http import ValidationError
from test_parties import company
from test_screening import create, person

GENERATED = datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)
FIXTURE = (Path(__file__).parent / "fixtures" / "un_consolidated_small.xml").read_bytes()


def variant(content=FIXTURE, generated="2026-10-08T09:00:00.000Z", drop=(), replace=()):
    """The fixture with another date, some entries dropped (by reference) and text replaced."""
    xml = content.decode("utf-8").replace('dateGenerated="2026-10-01T09:00:00.000Z"', f'dateGenerated="{generated}"')
    for ref in drop:
        xml = re.sub(rf"<(INDIVIDUAL|ENTITY)>(?:(?!</\1>).)*?<REFERENCE_NUMBER>{re.escape(ref)}</REFERENCE_NUMBER>"
                     rf".*?</\1>", "", xml, flags=re.S)
    for old, new in replace:
        assert old in xml
        xml = xml.replace(old, new)
    return xml.encode("utf-8")


def run(content=FIXTURE, **kw):
    return sanctions_un.import_xml(content, "test fixture", "scheduler", **kw)


def entries(status="active"):
    return {e.external_ref: e for e in WatchlistEntry.query.filter_by(list="sanctions_un", status=status)}


def set_setting(maker, checker, key, value):
    res = maker.post(f"/api/v1/settings/business/{key}",
                     {"value": value, "source": "client_confirmed", "evidence": "Compliance confirmation"})
    assert res.status_code == 201, res.get_json()
    res = checker.post(f"/api/v1/change-requests/{res.get_json()['data']['id']}/approve")
    assert res.status_code == 200, res.get_json()
    business.clear_cache()


def enable_un_screening(admin1, admin2):
    set_setting(admin1, admin2, "screening.lists_enabled", ["internal_blacklist", "pep", "sanctions_un"])


def audit_count(action):
    return db.session.execute(text("SELECT count(*) FROM audit_logs WHERE action = :a"), {"a": action}).scalar()


# ── Parsing ──


def test_parse_reads_individuals_entities_aliases_and_identifiers():
    parsed = sanctions_un.parse(FIXTURE)
    assert parsed.generated_at == GENERATED
    by_ref = {e.ref: e for e in parsed.entries}
    assert set(by_ref) == {"QDi.901", "SOi.902", "QDe.903"}
    omari = by_ref["QDi.901"]
    assert omari.kind == "individual" and omari.full_name == "OMARI TESTA KIPRONO"
    assert [a["name"] for a in omari.aliases] == ["Abu Testa", "Omari Kiprono"]  # empty alias skipped
    assert omari.aliases[1]["quality"] == "Low"
    assert [(i["id_type"], i["value_normalised"]) for i in omari.identifiers] == [
        ("passport", "AK990011"), ("national_id", "99887766")]  # "Other" documents aren't matched on
    assert omari.details["date_of_birth"] == ["1971-02-03"] and omari.details["un_list_type"] == "Al-Qaida"
    assert by_ref["SOi.902"].details["date_of_birth"] == ["1980–1982"]
    entity = by_ref["QDe.903"]
    assert entity.kind == "entity" and entity.full_name == "EXAMPLE RELIEF TRADING COMPANY"
    assert [a["name"] for a in entity.aliases] == ["ERTC Holdings"] and entity.identifiers == []


@pytest.mark.parametrize("content, message", [
    (b"<CONSOLIDATED_LIST", "valid XML"),
    (b"<OTHER_LIST dateGenerated='2026-10-01T00:00:00Z'/>", "CONSOLIDATED_LIST"),
    (b"<CONSOLIDATED_LIST dateGenerated='2026-10-01T00:00:00Z'><INDIVIDUALS/></CONSOLIDATED_LIST>", "no entries"),
    (b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><CONSOLIDATED_LIST/>', "DTD"),
    (variant(replace=[('dateGenerated="2026-10-08T09:00:00.000Z"', 'dateGenerated="soon"')]), "dateGenerated"),
])
def test_parse_refuses_bad_files(content, message):
    with pytest.raises(ValidationError, match=message):
        sanctions_un.parse(content)
    assert WatchlistEntry.query.count() == 0


# ── Importing ──


def test_import_adds_entries_records_the_version_and_is_idempotent():
    result = run()
    assert result["status"] == "applied" and (result["added"], result["updated"], result["removed"]) == (3, 0, 0)
    record = db.session.get(SanctionsListImport, result["id"])
    assert record.list_generated_at == GENERATED and record.entries_in_list == 3
    assert len(record.content_sha256) == 64 and record.imported_by == "scheduler"
    omari = entries()["QDi.901"]
    assert omari.full_name == "OMARI TESTA KIPRONO" and omari.name_normalised == "KIPRONO OMARI TESTA"
    assert omari.import_id == record.id and omari.added_by == "scheduler" and "QDi.901" in omari.reason
    assert omari.to_dict()["aliases"] == ["Abu Testa", "Omari Kiprono"]
    assert audit_count("IMPORT_SANCTIONS_LIST") == 1

    # The same file again (a retried job, a second worker) changes and records nothing.
    again = run()
    assert again == {"status": "unchanged", "import_id": record.id, "list_generated_at": record.list_generated_at.isoformat()}
    assert WatchlistEntry.query.count() == 3 and SanctionsListImport.query.count() == 1
    assert audit_count("IMPORT_SANCTIONS_LIST") == 1


def test_a_new_version_updates_removes_by_marking_and_relists_as_a_new_row():
    run()
    first = entries()
    v2 = variant(drop=["SOi.902"], replace=[("<ALIAS_NAME>Abu Testa</ALIAS_NAME>", "<ALIAS_NAME>Abu Testa Junior</ALIAS_NAME>")])
    result = run(v2)
    assert (result["added"], result["updated"], result["removed"]) == (0, 1, 1)
    removed = db.session.get(WatchlistEntry, first["SOi.902"].id)
    assert removed.status == "removed" and removed.removed_by == "scheduler" and removed.removed_at is not None
    assert removed.import_id == result["id"]
    omari = db.session.get(WatchlistEntry, first["QDi.901"].id)
    assert [a["name"] for a in omari.aliases] == ["Abu Testa Junior", "Omari Kiprono"]
    assert db.session.get(WatchlistEntry, first["QDe.903"].id).import_id != result["id"]  # unchanged, untouched

    # Listed again later: a new row, the removed one stays as it was.
    result = run(variant(generated="2026-10-15T09:00:00.000Z",
                         replace=[("<ALIAS_NAME>Abu Testa</ALIAS_NAME>", "<ALIAS_NAME>Abu Testa Junior</ALIAS_NAME>")]))
    assert (result["added"], result["updated"], result["removed"]) == (1, 0, 0)
    assert entries()["SOi.902"].id != removed.id and db.session.get(WatchlistEntry, removed.id).status == "removed"
    assert WatchlistEntry.query.filter_by(list="sanctions_un").count() == 4
    assert SanctionsListImport.query.count() == 3


def test_an_older_copy_is_refused():
    run(variant(generated="2026-10-08T09:00:00.000Z"))
    with pytest.raises(ValidationError, match="older than the one already imported"):
        run(FIXTURE)
    db.session.rollback()
    assert SanctionsListImport.query.count() == 1


def test_manual_sanctions_entries_are_left_alone(admin1):
    res = admin1.post("/api/v1/watchlist", {"list": "sanctions_un", "full_name": "Manual Entry",
                                            "reason": "Added by compliance", "source": "Gazette"})
    assert res.status_code == 201
    run()
    run(variant(drop=["QDi.901", "SOi.902", "QDe.903"],
                replace=[("<ENTITIES>", "<ENTITIES><ENTITY><FIRST_NAME>NEW CO</FIRST_NAME>"
                                        "<REFERENCE_NUMBER>QDe.999</REFERENCE_NUMBER></ENTITY>")]))
    manual = db.session.get(WatchlistEntry, res.get_json()["data"]["id"])
    assert manual.status == "active" and manual.external_ref is None


def test_mass_removal_is_refused_unless_forced(monkeypatch):
    monkeypatch.setattr(sanctions_un, "MASS_REMOVAL_MIN", 1)
    run()
    shrunk = variant(drop=["QDi.901", "SOi.902"])
    with pytest.raises(ValidationError, match="would remove 2 of 3"):
        run(shrunk)
    db.session.rollback()
    assert len(entries()) == 3
    assert run(shrunk, allow_mass_removal=True)["removed"] == 2
    assert set(entries()) == {"QDe.903"}


def test_database_allows_one_active_entry_per_reference():
    run()
    with pytest.raises(IntegrityError, match="uq_watchlist_entries_external_ref"):
        db.session.execute(text(
            "INSERT INTO watchlist_entries (list, full_name, name_normalised, reason, status, added_by, added_at,"
            " external_ref) VALUES ('sanctions_un', 'X', 'X', 'r', 'active', 'x', now(), 'QDi.901')"))
        db.session.flush()
    db.session.rollback()


def test_watchlist_rows_are_never_deleted_by_an_import():
    run()
    ids = {e.id for e in WatchlistEntry.query}
    run(variant(drop=["SOi.902"]))
    assert {e.id for e in WatchlistEntry.query} == ids


# ── Screening against the list ──


def test_clients_are_screened_on_alias_and_passport_once_the_list_is_enabled(staff, admin1, admin2):
    alias = create(staff, person(first="Abu", last="Testa", id_number="30111222", phone="0722000111"))["data"]
    run()
    # Not on screening.lists_enabled yet: imported, but nobody is matched.
    assert ScreeningResult.query.filter_by(party_id=alias["id"], review_status="pending").count() == 0

    enable_un_screening(admin1, admin2)
    passport = create(staff, person(first="Other", last="Name", id_number=None, phone="0722000222",
                                    identifiers=[{"id_type": "passport", "value": "ak-990011"}]))["data"]
    [hit] = ScreeningResult.query.filter_by(party_id=passport["id"], review_status="pending").one().matches
    assert hit["list"] == "sanctions_un" and hit["matched_on"] == ["identifier"]

    org = create(staff, company(organisation={"legal_name": "ERTC Holdings", "org_type": "sme",
                                              "registration_date": "2015-06-01"}))["data"]
    [hit] = ScreeningResult.query.filter_by(party_id=org["id"], review_status="pending").one().matches
    assert hit["name"] == "EXAMPLE RELIEF TRADING COMPANY (alias ERTC Holdings)" and hit["matched_on"] == ["name"]

    # The existing client is caught by the daily re-screen; a confirmed match blacklists them.
    assert TASKS["screening.rescreen"].fn({})["recorded"] == 1
    result = ScreeningResult.query.filter_by(party_id=alias["id"], review_status="pending").one()
    assert result.matches[0]["name"] == "OMARI TESTA KIPRONO (alias Abu Testa)"
    res = admin1.post(f"/api/v1/screening-results/{result.id}/review",
                      {"decision": "confirmed", "note": "Same person: date of birth and photo match."})
    assert res.status_code == 200 and db.session.get(Party, alias["id"]).status == "blacklisted"


def test_an_import_screens_clients_against_what_changed(staff, admin1, admin2):
    enable_un_screening(admin1, admin2)
    jane = create(staff, person(first="Samira", last="Exempla"))["data"]
    result = run()
    assert result["matched_parties"] == 1
    pending = ScreeningResult.query.filter_by(party_id=jane["id"], review_status="pending").one()
    assert pending.trigger == "watchlist_change" and pending.screened_by == "scheduler"
    # A later version that only changes someone else doesn't raise it again.
    assert run(variant(replace=[("<ALIAS_NAME>Abu Testa</ALIAS_NAME>", "<ALIAS_NAME>Abu T</ALIAS_NAME>")]))[
        "matched_parties"] == 0
    assert ScreeningResult.query.filter_by(party_id=jane["id"]).count() == 2  # onboarding + the import


# ── The job and its settings ──


def test_job_is_daily_and_off_by_default(monkeypatch):
    assert PERIODIC_BY_NAME["screening.un_sanctions_import"].kind == "daily"
    assert business.get("screening.un_sanctions.import_enabled") is False
    assert "sanctions_un" not in business.get("screening.lists_enabled")

    def no_download(url):
        raise AssertionError("must not download while the import is off")
    monkeypatch.setattr(sanctions_un, "download", no_download)
    assert TASKS["screening.un_sanctions_import"].fn({}) == {"status": "disabled"}


def test_job_downloads_from_the_configured_source_when_enabled(monkeypatch, admin1, admin2):
    set_setting(admin1, admin2, "screening.un_sanctions.import_enabled", True)
    urls = []
    monkeypatch.setattr(sanctions_un, "download", lambda url: urls.append(url) or FIXTURE)
    result = TASKS["screening.un_sanctions_import"].fn({})
    assert result["status"] == "applied" and result["added"] == 3
    assert urls == ["https://scsanctions.un.org/resources/xml/en/consolidated.xml"]
    assert SanctionsListImport.query.one().source == urls[0]
    assert TASKS["screening.un_sanctions_import"].fn({})["status"] == "unchanged"


def test_source_url_needs_two_approvers_and_https(admin1, admin2, staff):
    res = admin1.post("/api/v1/settings/business/screening.un_sanctions.source_url",
                      {"value": "http://example.org/list.xml", "source": "client_confirmed", "evidence": "x"})
    assert res.status_code == 400
    assert staff.post("/api/v1/settings/business/screening.un_sanctions.source_url",
                      {"value": "https://example.org/list.xml"}).status_code == 403
    res = admin1.post("/api/v1/settings/business/screening.un_sanctions.source_url",
                      {"value": "https://mirror.example.org/consolidated.xml", "source": "client_confirmed",
                       "evidence": "Compliance memo"})
    assert res.status_code == 201 and res.get_json()["data"]["request_type"] == "settings.change_security"
    with pytest.raises(ValidationError):
        normalise("screening.un_sanctions.source_url", "ftp://example.org/list.xml")


def test_cli_imports_a_local_file(app, tmp_path):
    path = tmp_path / "consolidated.xml"
    path.write_bytes(FIXTURE)
    out = app.test_cli_runner().invoke(args=["import-un-sanctions", "--file", str(path)])
    assert out.exit_code == 0, out.output
    record = SanctionsListImport.query.one()
    assert record.imported_by == "cli:import-un-sanctions" and record.source == "file:consolidated.xml"
    path.write_bytes(b"<nope")
    out = app.test_cli_runner().invoke(args=["import-un-sanctions", "--file", str(path)])
    assert out.exit_code != 0 and "valid XML" in out.output


# ── Accents ──


def test_names_match_with_or_without_accents(staff, admin1, admin2):
    from app.Parties.normalise import normalise_name
    assert normalise_name("Al-Qaïda Organisation") == normalise_name("al qaida organisation") == "AL ORGANISATION QAIDA"
    assert normalise_name("José Ñúñez") == "JOSE NUNEZ"
    enable_un_screening(admin1, admin2)
    run(variant(replace=[("<FIRST_NAME>SAMIRA</FIRST_NAME>", "<FIRST_NAME>SAMÍRA</FIRST_NAME>")]))
    client = create(staff, person(first="Samira", last="Exempla"))["data"]
    [hit] = ScreeningResult.query.filter_by(party_id=client["id"], review_status="pending").one().matches
    assert hit["name"] == "SAMÍRA EXEMPLA" and hit["matched_on"] == ["name"]


def test_migration_recomputes_stored_names_with_accents_folded(app):
    from flask_migrate import downgrade, upgrade

    def alembic(fn, revision):
        db.session.commit()
        db.session.remove()
        fn(revision=revision)

    alembic(downgrade, "c5d6e7f8a9b0")
    try:
        db.session.execute(text(
            "INSERT INTO watchlist_entries (list, full_name, name_normalised, aliases, reason, status, added_by,"
            " added_at) VALUES ('internal_blacklist', 'Zoë Kamau', 'KAMAU ZO', "
            "CAST('[{\"name\": \"Zoë K\", \"name_normalised\": \"K ZO\"}]' AS jsonb), 'r', 'active', 'x', now())"))
    finally:
        alembic(upgrade, "head")
    entry = WatchlistEntry.query.one()
    assert entry.name_normalised == "KAMAU ZOE" and entry.aliases[0]["name_normalised"] == "K ZOE"
