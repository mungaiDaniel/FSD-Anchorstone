"""Phase 2b item 3: duplicate warnings, blacklist screening and PEP approval (FSD v0.1 KYC-05, 06, 07)."""
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.database.database import db
from app.Jobs.registry import PERIODIC_BY_NAME, TASKS
from app.Parties.model import Party, ScreeningResult


def person(first="Jane", last="Doe", id_number="12345678", phone="0712345678", email=None, **over):
    body = {"party_type": "person", "person": {"first_name": first, "last_name": last, "date_of_birth": "1985-04-12"},
            "identifiers": [{"id_type": "national_id", "value": id_number}] if id_number else [],
            "contacts": [{"kind": "mobile", "value": phone}] + ([{"kind": "email", "value": email}] if email else []),
            "addresses": [{"kind": "home", "line1": "Riverside Dr"}]}
    body.update(over)
    return body


def create(api, body, expect=201):
    res = api.post("/api/v1/parties", body)
    assert res.status_code == expect, res.get_json()
    return res.get_json()


# ── KYC-05: duplicate warnings ──


def test_kyc_05_same_phone_warns_not_blocks(staff):
    first = create(staff, person())["data"]
    res = create(staff, person(first="John", last="Otieno", id_number="22981045", phone="+254 712 345 678"))
    assert res["data"]["party_no"] == "P-0000002"  # created anyway
    [warning] = res["data"]["warnings"]
    assert warning["kind"] == "mobile" and warning["party"]["id"] == first["id"]
    assert warning["message"] == "This phone number already belongs to P-0000001 (Jane Doe)."
    assert "duplicate warnings" in res["message"]


def test_kyc_05_same_email_warns(staff):
    create(staff, person(email="family@example.com"))
    res = create(staff, person(first="J", last="D", id_number=None, phone="0799000000", email="FAMILY@example.com"))
    assert [w["kind"] for w in res["data"]["warnings"]] == ["email"]


def test_kyc_05_check_duplicates_before_saving(staff):
    jane = create(staff, person(email="jane@example.com"))["data"]
    res = staff.post("/api/v1/parties/check-duplicates", {
        "party_type": "person", "identifiers": [{"id_type": "national_id", "value": "12-345-678"}],
        "contacts": [{"kind": "mobile", "value": "0712 345 678"}, {"kind": "email", "value": "new@example.com"}]})
    data = res.get_json()["data"]
    assert [c["party"]["id"] for c in data["conflicts"]] == [jane["id"]]
    assert "already registered to P-0000001" in data["conflicts"][0]["message"]
    assert [w["kind"] for w in data["warnings"]] == ["mobile"]
    # Editing the same client doesn't warn about its own details.
    res = staff.post("/api/v1/parties/check-duplicates", {
        "exclude_party_id": jane["id"], "identifiers": [{"id_type": "national_id", "value": "12345678"}],
        "contacts": [{"kind": "mobile", "value": "0712345678"}]})
    assert res.get_json()["data"] == {"conflicts": [], "warnings": []}


def test_kyc_05_related_parties_are_linked(staff):
    jane = create(staff, person())["data"]
    john = create(staff, person(first="John", last="Doe", id_number="22981045", phone="0722118904"))["data"]
    res = staff.post(f"/api/v1/parties/{jane['id']}/relationships", {"relationship": "related_party",
                                                                    "related_party_id": john["id"]})
    assert res.status_code == 201
    rels = staff.get(f"/api/v1/parties/{john['id']}").get_json()["data"]["relationships"]
    assert rels[0]["relationship"] == "related_party" and rels[0]["party"]["id"] == jane["id"]


# ── KYC-06: blacklist ──


def blacklist(api, name="Jane Doe", identifiers=None, list_="internal_blacklist", expect=201):
    res = api.post("/api/v1/watchlist", {"list": list_, "full_name": name, "identifiers": identifiers or [],
                                         "reason": "Defaulted on a loan elsewhere", "source": "Credit committee"})
    assert res.status_code == expect, res.get_json()
    return res.get_json()


def test_kyc_06_blacklist_match_blocks_verification_until_reviewed(staff, admin1):
    blacklist(admin1, "DOE, Jane")
    jane = create(staff, person(email="jane@example.com"))["data"]
    staff.post(f"/api/v1/parties/{jane['id']}/relationships",
               {"relationship": "next_of_kin", "related": {"person": {"first_name": "Kin", "last_name": "Doe"}}})
    jane = staff.get(f"/api/v1/parties/{jane['id']}").get_json()["data"]
    assert jane["screening"]["pending"] == 1 and jane["screening"]["last"]["matches"][0]["matched_on"] == ["name"]
    assert "watchlist match must be reviewed" in " ".join(jane["verification_blockers"])
    res = staff.post(f"/api/v1/parties/{jane['id']}/verify", {"reason": "KYC complete"})
    assert res.status_code == 400 and "watchlist" in res.get_json()["message"]

    [row] = admin1.get("/api/v1/screening-results").get_json()["data"]["items"]
    assert row["party"]["id"] == jane["id"]
    assert admin1.post(f"/api/v1/screening-results/{row['id']}/review", {"decision": "clear"}).status_code == 400
    res = admin1.post(f"/api/v1/screening-results/{row['id']}/review",
                      {"decision": "clear", "note": "Different person: other ID and date of birth."})
    assert res.status_code == 200 and res.get_json()["data"]["review_status"] == "cleared"
    assert admin1.post(f"/api/v1/screening-results/{row['id']}/review",
                       {"decision": "clear", "note": "again"}).status_code == 409
    jane = staff.get(f"/api/v1/parties/{jane['id']}").get_json()["data"]
    assert not any("watchlist" in b for b in jane["verification_blockers"])


def test_kyc_06_confirmed_match_blacklists_the_client(staff, admin1):
    blacklist(admin1, "Someone Else", identifiers=[{"id_type": "national_id", "value": "12 345 678"}])
    jane = create(staff, person())["data"]
    result = ScreeningResult.query.filter_by(party_id=jane["id"]).one()
    assert result.matches[0]["matched_on"] == ["identifier"] and result.trigger == "onboarding"
    res = admin1.post(f"/api/v1/screening-results/{result.id}/review", {"decision": "confirmed", "note": "Same ID."})
    assert res.status_code == 200
    assert db.session.get(Party, jane["id"]).status == "blacklisted"
    res = staff.post(f"/api/v1/parties/{jane['id']}/verify")
    assert res.status_code == 400 and "blacklisted" in res.get_json()["message"]


def test_kyc_06_maker_cannot_review_own_party(staff, admin1, admin2):
    blacklist(admin2, "Jane Doe")
    jane = create(admin1, person())["data"]  # onboarded by admin1
    result = ScreeningResult.query.filter_by(party_id=jane["id"]).one()
    res = admin1.post(f"/api/v1/screening-results/{result.id}/review", {"decision": "clear", "note": "fine"})
    assert res.status_code == 403 and "Maker-checker" in res.get_json()["message"]
    # Staff hold no screening.review at all.
    assert staff.post(f"/api/v1/screening-results/{result.id}/review", {"decision": "clear", "note": "x"}).status_code == 403
    assert staff.get("/api/v1/screening-results").status_code == 403
    assert admin2.post(f"/api/v1/screening-results/{result.id}/review",
                       {"decision": "clear", "note": "fine"}).status_code == 200


def test_kyc_06_database_refuses_review_by_the_maker(admin1, admin2):
    blacklist(admin2, "Jane Doe")
    jane = create(admin1, person())["data"]
    result = ScreeningResult.query.filter_by(party_id=jane["id"]).one()
    with pytest.raises(IntegrityError, match="ck_screening_results_maker_not_checker"):
        db.session.execute(text("UPDATE screening_results SET review_status = 'cleared', "
                                "reviewed_by = 'ADMIN1@anchorstone.test', reviewed_at = now() WHERE id = :i"),
                           {"i": result.id})
        db.session.flush()
    db.session.rollback()


def test_kyc_06_existing_parties_rescreened(staff, admin1, make_investor):
    inv = make_investor(full_name="Peter Kamau Njoroge", id_number="22981045")
    jane = create(staff, person())["data"]
    assert TASKS["screening.rescreen"] and PERIODIC_BY_NAME["screening.rescreen"].kind == "daily"
    run = TASKS["screening.rescreen"].fn
    first = run({})
    assert first == {"screened": 2, "recorded": 0}  # both were screened when created, nothing new

    # A name added to the list later is caught by the next daily run (and right away by the add itself).
    res = blacklist(admin1, "Peter Kamau Njoroge")
    assert res["data"]["matched_parties"] == 1
    from app.Investors.model import Investor
    party_id = db.session.get(Investor, inv["id"]).party_id
    assert ScreeningResult.query.filter_by(party_id=party_id, review_status="pending").count() == 1
    assert run({}) == {"screened": 2, "recorded": 0}  # idempotent: same match isn't recorded again
    assert ScreeningResult.query.filter_by(party_id=party_id).count() == 2
    assert ScreeningResult.query.filter_by(party_id=jane["id"]).count() == 1
    audit = db.session.execute(text("SELECT count(*) FROM audit_logs WHERE action = 'SCREENING_MATCH'")).scalar()
    assert audit == 1


def test_kyc_06_lists_follow_the_setting(staff, admin1, admin2):
    blacklist(admin1, "Jane Doe", list_="sanctions_un")  # not enabled by default
    jane = create(staff, person())["data"]
    assert ScreeningResult.query.filter_by(party_id=jane["id"]).one().outcome == "clear"


def test_kyc_06_watchlist_removal_is_maker_checker(admin1, admin2, staff):
    entry = blacklist(admin1)["data"]
    assert blacklist(staff, expect=403)
    assert admin1.post("/api/v1/watchlist", {"list": "internal_blacklist", "full_name": "X"}).status_code == 400
    res = admin1.post(f"/api/v1/watchlist/{entry['id']}/remove", {"reason": "Debt repaid; credit committee 12 Oct."})
    assert res.status_code == 201
    cr = res.get_json()["data"]
    assert admin1.post(f"/api/v1/change-requests/{cr['id']}/approve").status_code == 403
    assert admin2.post(f"/api/v1/change-requests/{cr['id']}/approve").status_code == 200
    assert admin1.get("/api/v1/watchlist").get_json()["data"]["total"] == 0


# ── KYC-07: PEP ──


PEP = {"is_pep": True, "position_held": "Member of County Assembly", "country": "KE", "since": "2022-08-09",
       "pep_relationship": "self", "source_of_funds": "Salary and rental income",
       "source_of_wealth": "Inherited farmland in Nakuru"}


def test_kyc_07_pep_requires_details(staff):
    jane = create(staff, person())["data"]
    for missing in ("position_held", "source_of_funds", "source_of_wealth", "pep_relationship"):
        res = staff.client.put(f"/api/v1/parties/{jane['id']}/pep", json={**PEP, missing: ""}, headers=staff.headers)
        assert res.status_code == 400, missing
    res = staff.client.put(f"/api/v1/parties/{jane['id']}/pep", json={**PEP, "pep_relationship": "family_member"},
                           headers=staff.headers)
    assert res.status_code == 400 and "related to" in res.get_json()["message"]
    assert db.session.get(Party, jane["id"]).is_pep is False


def _flag(api, party_id, body=None):
    res = api.client.put(f"/api/v1/parties/{party_id}/pep", json=body or PEP, headers=api.headers)
    assert res.status_code == 201, res.get_json()
    return res.get_json()["data"]


def test_kyc_07_pep_needs_two_approvers(staff, admin1, admin2, superadmin):
    jane = create(staff, person())["data"]
    cr = _flag(staff, jane["id"])
    assert cr["request_type"] == "party.pep_approve" and cr["levels"] == [{"permission": "kyc.pep.approve", "count": 2}]
    detail = staff.get(f"/api/v1/parties/{jane['id']}").get_json()["data"]
    assert detail["is_pep"] is True and detail["pep"]["status"] == "pending"
    assert any("senior approval" in b for b in detail["verification_blockers"])
    # A second PEP change can't be stacked on top.
    assert staff.client.put(f"/api/v1/parties/{jane['id']}/pep", json=PEP, headers=staff.headers).status_code == 409

    assert staff.post(f"/api/v1/change-requests/{cr['id']}/approve").status_code == 403  # no kyc.pep.approve
    res = admin1.post(f"/api/v1/change-requests/{cr['id']}/approve")
    assert res.status_code == 200 and res.get_json()["data"]["status"] == "pending"  # one of two
    assert admin1.post(f"/api/v1/change-requests/{cr['id']}/approve").status_code == 403  # not twice
    assert staff.get(f"/api/v1/parties/{jane['id']}").get_json()["data"]["pep"]["status"] == "pending"
    res = admin2.post(f"/api/v1/change-requests/{cr['id']}/approve")
    assert res.status_code == 200 and res.get_json()["data"]["status"] == "applied"
    detail = staff.get(f"/api/v1/parties/{jane['id']}").get_json()["data"]
    assert detail["pep"]["status"] == "approved"
    assert detail["pep"]["approved_by"] == "admin1@anchorstone.test, admin2@anchorstone.test"
    assert not any("PEP" in b for b in detail["verification_blockers"])

    # Clearing the flag needs the same approval.
    clear = staff.client.put(f"/api/v1/parties/{jane['id']}/pep", json={"is_pep": False}, headers=staff.headers)
    cr = clear.get_json()["data"]
    assert db.session.get(Party, jane["id"]).is_pep is True
    admin1.post(f"/api/v1/change-requests/{cr['id']}/approve")
    superadmin.post(f"/api/v1/change-requests/{cr['id']}/approve")
    db.session.expire_all()
    assert db.session.get(Party, jane["id"]).is_pep is False


def test_kyc_07_maker_cannot_approve(admin1, admin2, superadmin):
    jane = create(admin1, person())["data"]
    cr = _flag(admin1, jane["id"])
    res = admin1.post(f"/api/v1/change-requests/{cr['id']}/approve")
    assert res.status_code == 403 and "Maker-checker" in res.get_json()["message"]
    maker = db.session.execute(text("SELECT id FROM \"user\" WHERE email = 'admin1@anchorstone.test'")).scalar()
    with pytest.raises(IntegrityError, match="Maker-checker"):
        db.session.execute(text(
            "INSERT INTO change_request_events (request_id, round, action, level, actor_user_id, actor_email, at, "
            "date_created, date_updated) VALUES (:r, 1, 'approve', 1, :u, 'admin1@anchorstone.test', now(), now(), now())"),
            {"r": cr["id"], "u": maker})
        db.session.flush()
    db.session.rollback()


def test_kyc_07_pep_captured_at_onboarding(staff):
    res = create(staff, {**person(), "pep": PEP})
    party_id = res["data"]["id"]
    detail = staff.get(f"/api/v1/parties/{party_id}").get_json()["data"]
    assert detail["is_pep"] and detail["pep"]["position_held"] == "Member of County Assembly"


def test_kyc_07_confirmed_pep_list_match_flags_the_client(staff, admin1):
    blacklist(admin1, "Jane Doe", list_="pep")
    jane = create(staff, person())["data"]
    result = ScreeningResult.query.filter_by(party_id=jane["id"]).one()
    admin1.post(f"/api/v1/screening-results/{result.id}/review", {"decision": "confirmed", "note": "MCA Nakuru"})
    detail = staff.get(f"/api/v1/parties/{jane['id']}").get_json()["data"]
    assert detail["is_pep"] and detail["status"] == "active"
    assert any("record the PEP details" in b for b in detail["verification_blockers"])
