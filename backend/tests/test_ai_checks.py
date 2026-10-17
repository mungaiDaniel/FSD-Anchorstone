"""Phase 3b, AI-06: cross-document checks, in code, on approved (confirmed) values only."""
import pytest

from app.Applications.checks import compare_names
from application_helpers import (add_director, new_application, organisation, person, read_into,
                                 review_and_approve)
from docai_fakes import recorded
from test_docai import ai, make_party  # noqa: F401 (ai is a fixture)


def checks(api, application_id):
    res = api.get(f"/api/v1/applications/{application_id}/checks")
    assert res.status_code == 200, res.get_json()
    return {c["check"]: c for c in res.get_json()["data"]}


@pytest.mark.parametrize("a, b, expected", [
    ("Testa Sample Mockerson", "TESTA SAMPLE MOCKERSON", "pass"),          # case
    ("  Testa   Sample Mockerson ", "Testa Sample Mockerson", "pass"),     # spacing
    ("Mockerson, Testa Sample", "Testa Sample Mockerson", "pass"),          # name order
    ("Dr. Testa Sample Mockerson", "TESTA SAMPLE MOCKERSON", "pass"),      # titles ignored
    ("Testa Mockerson", "Testa Sample Mockerson", "needs_review"),          # missing middle name: never a pass
    ("Testa Sample Mokerson", "Testa Sample Mockerson", "needs_review"),    # one letter off: fuzzy, never a pass
    ("Exempla Dummy", "Testa Sample Mockerson", "fail"),
    (None, "Testa", "missing"),
])
def test_ai_06_name_comparison_allows_case_spacing_and_order_but_flags_fuzzy(a, b, expected):
    assert compare_names(a, b) == expected


def test_ai_06_name_and_id_match_across_id_kra_pin_and_application(ai, staff, admin1, admin2):
    p = person(staff)
    app = new_application(staff, p["id"])
    before = checks(staff, app["id"])
    assert before["name_consistent"]["status"] == "missing"  # nothing approved yet: never a pass
    for doc_type in ("national_id", "kra_pin"):
        ex = read_into(ai, staff, admin1, app, p["id"], doc_type, doc_type if doc_type != "national_id"
                       else "national_id_clean")
        review_and_approve(admin1, admin2, ex.id)
    got = checks(staff, app["id"])
    assert got["name_consistent"]["status"] == "pass", got["name_consistent"]
    sources = {e["source"] for e in got["name_consistent"]["evidence"]}
    assert sources == {"application (client record)", "National ID", "KRA PIN certificate"}
    assert got["id_number_consistent"]["status"] == "pass", got["id_number_consistent"]  # PIN filled by approval
    assert got["cr12_directors_match"]["status"] == "not_applicable"
    assert got["collateral_owner_match"]["status"] == "missing"  # business loan without collateral documents


def test_ai_06_a_different_id_number_fails_and_a_close_name_needs_review(ai, staff, admin1, admin2):
    p = person(staff, first="Testa", last="Mockerson", id_number="00000009")
    app = new_application(staff, p["id"])
    ex = read_into(ai, staff, admin1, app, p["id"], "national_id", "national_id_clean")
    review_and_approve(admin1, admin2, ex.id)
    got = checks(staff, app["id"])
    assert got["id_number_consistent"]["status"] == "fail"
    assert "National ID shows 00000001, the record 00000009" in got["id_number_consistent"]["reason"]
    assert got["name_consistent"]["status"] == "needs_review"  # the record lacks the middle name


def test_ai_06_cr12_directors_against_captured_directors(ai, staff, admin1, admin2):
    org = organisation(staff)
    testa = make_party(staff, "Testa Sample", "Mockerson", "00000001")
    add_director(staff, org["id"], testa["id"])
    app = new_application(staff, org["id"])
    ex = read_into(ai, staff, admin1, app, org["id"], "cr12", "cr12")
    review_and_approve(admin1, admin2, ex.id)
    got = checks(staff, app["id"])["cr12_directors_match"]
    assert got["status"] == "fail"
    assert got["reason"] == "On the CR12 but not captured: EXEMPLA DUMMY PLACEHOLDER."
    exempla = make_party(staff, "Exempla Dummy", "Placeholder", "00000002")
    add_director(staff, org["id"], exempla["id"])
    assert checks(staff, app["id"])["cr12_directors_match"]["status"] == "pass"
    other = make_party(staff, "Third", "Director", "00000003")
    add_director(staff, org["id"], other["id"])
    got = checks(staff, app["id"])["cr12_directors_match"]
    assert got["status"] == "fail" and "Captured but not on the CR12: Third Director" in got["reason"]


def test_ai_06_collateral_owner_is_the_applicant_or_a_guarantor(ai, staff, admin1, admin2):
    applicant = person(staff, "Exempla Dummy", "Placeholder", "00000002")
    owner = person(staff)  # TESTA SAMPLE MOCKERSON owns the sample vehicle
    app = new_application(staff, applicant["id"])
    staff.post(f"/api/v1/applications/{app['id']}/guarantors", {"party_id": owner["id"]})
    ex = read_into(ai, staff, admin1, app, owner["id"], "logbook", "logbook")
    review_and_approve(admin1, admin2, ex.id)
    assert checks(staff, app["id"])["collateral_owner_match"]["status"] == "pass"

    stranger_app = new_application(staff, applicant["id"])
    answer = recorded("logbook")["answer"]
    answer["fields"]["registered_owners"]["value"] = "SOMEONE ELSE ENTIRELY"
    answer["fields"]["financier_interest"]["value"] = "SAMPLE BANK LTD"
    ex = read_into(ai, staff, admin1, stranger_app, applicant["id"], "logbook", "logbook",
                   answers={"logbook": answer})
    review_and_approve(admin1, admin2, ex.id)
    got = checks(staff, stranger_app["id"])["collateral_owner_match"]
    assert got["status"] == "fail" and "SOMEONE ELSE ENTIRELY is neither the applicant nor a guarantor" in got["reason"]
    assert "financier interest: SAMPLE BANK LTD" in got["reason"]

    bridge = new_application(staff, applicant["id"], product_code="bridge_loan", term_months=2)
    assert checks(staff, bridge["id"])["collateral_owner_match"]["status"] == "not_applicable"


def test_ai_06_unapproved_readings_are_ignored(ai, staff, admin1):
    p = person(staff)
    app = new_application(staff, p["id"])
    read_into(ai, staff, admin1, app, p["id"], "national_id", "national_id_clean")  # read, not reviewed
    assert checks(staff, app["id"])["name_consistent"]["status"] == "missing"
