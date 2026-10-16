"""Phase 2b item 4: maker-checker on identity, bank and payout details (FSD v0.1 KYC-08, WA-01)."""
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.database.database import db
from app.Investors.model import Investor
from app.Parties.model import Party, PartyIdentifier, ScreeningResult


def jane(api, **over):
    body = {"party_type": "person",
            "person": {"first_name": "Jane", "last_name": "Doe", "date_of_birth": "1985-04-12", "gender": "female"},
            "identifiers": [{"id_type": "national_id", "value": "12345678"}, {"id_type": "kra_pin", "value": "A012345678K"}],
            "contacts": [{"kind": "mobile", "value": "0712345678"}, {"kind": "email", "value": "jane@example.com"}],
            "addresses": [{"kind": "home", "line1": "Riverside Dr"}],
            "bank_accounts": [{"kind": "mpesa", "account_no": "0712345678"}]}
    body.update(over)
    res = api.post("/api/v1/parties", body)
    assert res.status_code == 201, res.get_json()
    return res.get_json()["data"]


def patch(api, party_id, body, expect=200):
    res = api.patch(f"/api/v1/parties/{party_id}", body)
    assert res.status_code == expect, res.get_json()
    return res.get_json()


NEW_ID = [{"id_type": "national_id", "value": "87654321"}, {"id_type": "kra_pin", "value": "A012345678K"}]


def test_kyc_08_id_change_creates_request_party_unchanged(staff):
    p = jane(staff)
    res = patch(staff, p["id"], {"identifiers": NEW_ID, "reason": "ID replaced after loss"})
    cr = res["data"]["change_request"]
    assert cr["request_type"] == "party.change" and cr["status"] == "pending"
    assert cr["payload"]["changes"]["groups"] == ["identity"] and res["data"]["saved"] == []
    assert "identity details change needs a second person's approval" in res["message"]
    ids = {i.id_type: i.value_display for i in PartyIdentifier.query.filter_by(party_id=p["id"])}
    assert ids["national_id"] == "12345678"
    assert cr["summary"] == f"Change identity details of {p['party_no']} Jane Doe"


def test_kyc_08_applies_after_other_user_approves(staff, admin1):
    p = jane(staff)
    cr = patch(staff, p["id"], {"identifiers": NEW_ID, "person": {"first_name": "Janet"}})["data"]["change_request"]
    res = admin1.post(f"/api/v1/change-requests/{cr['id']}/approve")
    assert res.status_code == 200 and res.get_json()["data"]["status"] == "applied"
    detail = staff.get(f"/api/v1/parties/{p['id']}").get_json()["data"]
    assert {i["value"] for i in detail["identifiers"] if i["id_type"] == "national_id"} == {"87654321"}
    assert detail["display_name"] == "Janet Doe" and detail["person"]["first_name"] == "Janet"
    # Re-screened on the identity change, and audited with old and new values.
    assert ScreeningResult.query.filter_by(party_id=p["id"], trigger="identity_change").count() == 1
    row = db.session.execute(text("SELECT old_value, new_value FROM audit_logs WHERE action = 'APPLY_PARTY_CHANGE'")).one()
    assert "12345678" in row.old_value and "87654321" in row.new_value


def test_kyc_08_maker_cannot_approve(admin1, admin2, staff):
    p = jane(admin1)
    cr = patch(admin1, p["id"], {"identifiers": NEW_ID})["data"]["change_request"]
    res = admin1.post(f"/api/v1/change-requests/{cr['id']}/approve")
    assert res.status_code == 403 and "Maker-checker" in res.get_json()["message"]
    assert staff.post(f"/api/v1/change-requests/{cr['id']}/approve").status_code == 403  # no party.change.approve
    maker = db.session.execute(text("SELECT id FROM \"user\" WHERE email = 'admin1@anchorstone.test'")).scalar()
    with pytest.raises(IntegrityError, match="Maker-checker"):
        db.session.execute(text(
            "INSERT INTO change_request_events (request_id, round, action, level, actor_user_id, actor_email, at, "
            "date_created, date_updated) VALUES (:r, 1, 'approve', 1, :u, 'admin1@anchorstone.test', now(), now(), now())"),
            {"r": cr["id"], "u": maker})
        db.session.flush()
    db.session.rollback()
    assert admin2.post(f"/api/v1/change-requests/{cr['id']}/approve").status_code == 200


def test_kyc_08_bank_and_payout_controlled(staff, admin1):
    p = jane(staff)
    two = [{"kind": "mpesa", "account_no": "0712345678"},
           {"kind": "bank", "bank_name": "KCB Bank", "account_no": "1145829364", "is_default_payout": True}]
    cr = patch(staff, p["id"], {"bank_accounts": two})["data"]["change_request"]
    assert cr["payload"]["changes"]["groups"] == ["bank"]
    assert len(staff.get(f"/api/v1/parties/{p['id']}").get_json()["data"]["bank_accounts"]) == 1
    admin1.post(f"/api/v1/change-requests/{cr['id']}/approve")
    banks = staff.get(f"/api/v1/parties/{p['id']}").get_json()["data"]["bank_accounts"]
    assert {(b["account_no"], b["is_default_payout"]) for b in banks} == {("0712345678", False), ("1145829364", True)}

    # Moving payouts back to M-Pesa only changes the default: the payout group.
    back = [{"kind": "mpesa", "account_no": "0712345678", "is_default_payout": True},
            {"kind": "bank", "bank_name": "KCB Bank", "account_no": "1145829364"}]
    cr = patch(staff, p["id"], {"bank_accounts": back})["data"]["change_request"]
    assert cr["payload"]["changes"]["groups"] == ["payout"]


def test_kyc_08_phone_and_email_save_directly_and_audited(staff):
    p = jane(staff)
    res = patch(staff, p["id"], {"contacts": [{"kind": "mobile", "value": "0722000111"},
                                              {"kind": "email", "value": "jane.doe@example.com"}],
                                 "addresses": [{"kind": "home", "line1": "New Hse, Kilimani"}],
                                 "person": {"marital_status": "married", "sector": "Trade"}, "risk_rating": "medium"})
    assert res["data"]["change_request"] is None and res["message"] == "Saved."
    assert sorted(res["data"]["saved"]) == ["address", "email", "other", "phone"]
    d = res["data"]
    assert {c["value"] for c in d["contacts"]} == {"0722000111", "jane.doe@example.com"}
    assert d["person"]["marital_status"] == "married" and d["risk_rating"] == "medium"
    row = db.session.execute(text("SELECT old_value, new_value, user_email FROM audit_logs "
                                  "WHERE action = 'UPDATE_PARTY'")).one()
    assert "0712345678" in row.old_value and "0722000111" in row.new_value and row.user_email == "staff@anchorstone.test"
    # Unchanged values don't count as an edit.
    assert patch(staff, p["id"], {"risk_rating": "medium"})["message"] == "Nothing changed."


def test_kyc_08_mixed_edit_saves_contacts_and_submits_identity(staff):
    p = jane(staff)
    res = patch(staff, p["id"], {"contacts": [{"kind": "mobile", "value": "0722000111"},
                                              {"kind": "email", "value": "jane@example.com"}],
                                 "person": {"date_of_birth": "1985-04-21"}})
    assert res["data"]["saved"] == ["phone"] and res["data"]["change_request"]["payload"]["changes"]["groups"] == ["identity"]
    assert res["data"]["person"]["date_of_birth"] == "1985-04-12"


def test_kyc_08_setting_adds_email_to_controlled_fields(staff, admin1, admin2):
    res = admin1.post("/api/v1/settings/business/kyc.maker_checker_fields",
                      {"value": ["identity", "bank", "payout", "email"], "source": "internal_decision",
                       "reason": "Statement email is a payout risk"})
    assert res.status_code == 201, res.get_json()
    assert admin2.post(f"/api/v1/change-requests/{res.get_json()['data']['id']}/approve").status_code == 200
    p = jane(staff)
    res = patch(staff, p["id"], {"contacts": [{"kind": "mobile", "value": "0712345678"},
                                              {"kind": "email", "value": "other@example.com"}]})
    assert res["data"]["saved"] == [] and res["data"]["change_request"]["payload"]["changes"]["groups"] == ["email"]


def test_kyc_08_stale_request_fails(staff, admin1):
    p = jane(staff)
    first = patch(staff, p["id"], {"identifiers": NEW_ID})["data"]["change_request"]
    second = patch(staff, p["id"], {"identifiers": [{"id_type": "national_id", "value": "11112222"}]})["data"]["change_request"]
    assert admin1.post(f"/api/v1/change-requests/{first['id']}/approve").status_code == 200
    res = admin1.post(f"/api/v1/change-requests/{second['id']}/approve")
    assert res.status_code == 409 and "changed after this request" in res.get_json()["message"]


def test_kyc_08_duplicate_id_refused_at_submit(staff):
    jane(staff)
    other = jane(staff, identifiers=[], person={"first_name": "Other", "last_name": "Person"}, contacts=[])
    res = staff.patch(f"/api/v1/parties/{other['id']}", {"identifiers": [{"id_type": "national_id", "value": "12 345 678"}]})
    assert res.status_code == 409 and "already registered to P-0000001" in res.get_json()["message"]


def test_kyc_08_verified_client_goes_back_to_review_after_identity_change(staff, admin1):
    p = jane(staff)
    staff.post(f"/api/v1/parties/{p['id']}/relationships",
               {"relationship": "next_of_kin", "related": {"person": {"first_name": "Kin", "last_name": "Doe"}}})
    cr = staff.post(f"/api/v1/parties/{p['id']}/verify").get_json()["data"]
    admin1.post(f"/api/v1/change-requests/{cr['id']}/approve")
    assert db.session.get(Party, p["id"]).kyc_status == "verified"
    cr = patch(staff, p["id"], {"identifiers": NEW_ID})["data"]["change_request"]
    admin1.post(f"/api/v1/change-requests/{cr['id']}/approve")
    db.session.expire_all()
    assert db.session.get(Party, p["id"]).kyc_status == "pending_review"


def test_kyc_08_investor_form_routes_identity_and_payout_for_approval(staff, admin1, make_investor):
    inv = make_investor(full_name="Jane Doe", id_number="12345678")
    res = staff.patch(f"/api/v1/investors/{inv['id']}", {"full_name": "Jane Wanjiru Doe", "phone": "0722000111",
                                                         "payout_account": "0799999999", "notes": "VIP"})
    assert res.status_code == 200 and "request #" in res.get_json()["message"]
    data = res.get_json()["data"]
    assert (data["full_name"], data["payout_account"]) == ("Jane Doe", "0700000000")  # waiting for approval
    assert (data["phone"], data["notes"]) == ("0722000111", "VIP")                  # saved at once
    [cr] = staff.get("/api/v1/change-requests?mine=1").get_json()["data"]["items"]
    assert cr["payload"]["groups"] == ["bank", "identity"]
    assert admin1.post(f"/api/v1/change-requests/{cr['id']}/approve").status_code == 200
    inv = staff.get(f"/api/v1/investors/{inv['id']}").get_json()["data"]
    assert (inv["full_name"], inv["payout_account"]) == ("Jane Wanjiru Doe", "0799999999")
    party = db.session.get(Party, db.session.get(Investor, inv["id"]).party_id)
    assert party.display_name == "Jane Wanjiru Doe"
    # Email stays a direct change (WA-01), and still one investor per email.
    assert staff.patch(f"/api/v1/investors/{inv['id']}", {"email": "jane2@example.com"}).get_json()["message"] == \
        "Investor updated."


def test_branch_is_not_changed_by_an_edit(staff):
    p = jane(staff)
    res = staff.patch(f"/api/v1/parties/{p['id']}", {"home_branch_id": 2})
    assert res.status_code == 400 and "branch transfer" in res.get_json()["message"]
