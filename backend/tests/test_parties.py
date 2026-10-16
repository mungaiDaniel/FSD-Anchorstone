"""Phase 2b item 1: parties, KYC fields, related parties and duplicate refusal (FSD v0.1 KYC-01 … 04, 11)."""
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.Access.model import Role
from app.Branches.model import Branch
from app.database.database import db
from app.Parties.model import Party, PartyIdentifier


def person(**over):
    body = {
        "party_type": "person",
        "classification": "retail",
        "person": {"salutation": "Ms", "first_name": "Jane", "middle_name": "Wanjiru", "last_name": "Doe",
                   "gender": "female", "date_of_birth": "1985-04-12", "marital_status": "married",
                   "sector": "Trade", "nature_of_business": "Retail shop", "employer_name": "Self-employed"},
        "identifiers": [{"id_type": "national_id", "value": "12 345 678"}, {"id_type": "kra_pin", "value": "a012345678k"}],
        "contacts": [{"kind": "mobile", "value": "0712 345 678"}, {"kind": "email", "value": "Jane@Example.com"}],
        "addresses": [{"kind": "home", "line1": "Hse 4, Riverside Dr", "town": "Nairobi", "county": "Nairobi"},
                      {"kind": "business", "line1": "Shop 2, Moi Ave", "town": "Nairobi"}],
        "bank_accounts": [{"kind": "mpesa", "account_no": "0712345678", "is_default_payout": True}],
        "risk_rating": "low",
    }
    body.update(over)
    return body


def company(**over):
    body = {
        "party_type": "organisation",
        "classification": "sme",
        "organisation": {"legal_name": "Acme Traders Ltd", "trading_name": "Acme", "registration_date": "2015-06-01",
                         "org_type": "sme", "sector": "Wholesale", "nature_of_business": "FMCG distribution"},
        "identifiers": [{"id_type": "company_reg_no", "value": "PVT-ABC123"}, {"id_type": "kra_pin", "value": "P051234567X"}],
        "contacts": [{"kind": "phone", "value": "020 2345678"}, {"kind": "email", "value": "info@acme.example"}],
        "addresses": [{"kind": "registered", "line1": "Acme House, Industrial Area", "town": "Nairobi"}],
        "bank_accounts": [{"kind": "bank", "bank_name": "Equity Bank", "branch_name": "Industrial Area",
                           "account_no": "0180293847561", "account_name": "Acme Traders Ltd"}],
        "risk_rating": "medium",
    }
    body.update(over)
    return body


def create(api, body, expect=201):
    res = api.post("/api/v1/parties", body)
    assert res.status_code == expect, res.get_json()
    return res.get_json()


def test_kyc_01_individual_fields_saved_and_returned(staff):
    data = create(staff, person())["data"]
    assert data["party_no"] == "P-0000001" and data["party_type"] == "person"
    assert data["display_name"] == "Jane Wanjiru Doe"
    p = data["person"]
    assert (p["salutation"], p["gender"], p["date_of_birth"], p["marital_status"]) == ("Ms", "female", "1985-04-12", "married")
    assert (p["sector"], p["nature_of_business"], p["employer_name"]) == ("Trade", "Retail shop", "Self-employed")
    assert data["classification"] == "retail" and data["risk_rating"] == "low" and data["home_branch_id"] == 1
    assert {(i["id_type"], i["value"]) for i in data["identifiers"]} == {("national_id", "12 345 678"),
                                                                        ("kra_pin", "a012345678k")}
    assert {c["kind"] for c in data["contacts"]} == {"mobile", "email"}
    assert {a["kind"] for a in data["addresses"]} == {"home", "business"}
    assert data["bank_accounts"][0]["is_default_payout"] is True
    assert data["is_pep"] is False and data["created_by"] == "staff@anchorstone.test"
    # Next of kin is still missing, so KYC can't be complete yet.
    assert data["kyc_status"] == "incomplete" and data["missing_fields"] == ["next_of_kin"]
    # Normalised for duplicate checks, shown as typed.
    row = PartyIdentifier.query.filter_by(id_type="kra_pin").one()
    assert row.value_normalised == "A012345678K"


def test_kyc_01_invalid_input_refused(staff):
    assert create(staff, person(person={"first_name": ""}), 400)
    assert "gender" in create(staff, person(person={"first_name": "A", "gender": "x"}), 400)["message"]
    assert "future" in create(staff, person(person={"first_name": "A", "date_of_birth": "2030-01-01"}), 400)["message"]
    assert "email" in create(staff, person(contacts=[{"kind": "email", "value": "nope"}]), 400)["message"]
    assert "company registration" in create(
        staff, person(identifiers=[{"id_type": "company_reg_no", "value": "X1"}]), 400)["message"]
    assert "investor role" in create(staff, person(roles=["investor"]), 400)["message"]


def test_kyc_02_company_with_directors_and_signatories(staff):
    org = create(staff, company())["data"]
    assert org["display_name"] == "Acme Traders Ltd" and org["organisation"]["org_type"] == "sme"
    assert org["organisation"]["registration_date"] == "2015-06-01"
    assert "director_with_id" in org["missing_fields"]

    res = staff.post(f"/api/v1/parties/{org['id']}/relationships", {
        "relationship": "director",
        "related": {"person": {"first_name": "John", "last_name": "Otieno", "date_of_birth": "1970-02-02"},
                    "identifiers": [{"id_type": "national_id", "value": "22981045"}],
                    "contacts": [{"kind": "mobile", "value": "0722118904"}]}})
    assert res.status_code == 201, res.get_json()
    director_id = res.get_json()["data"]["from_party_id"]
    res = staff.post(f"/api/v1/parties/{org['id']}/relationships",
                     {"relationship": "shareholder", "related_party_id": director_id, "share_pct": "60"})
    assert res.status_code == 201, res.get_json()
    res = staff.post(f"/api/v1/parties/{org['id']}/relationships",
                     {"relationship": "signatory", "related_party_id": director_id, "signatory_list": "A"})
    assert res.status_code == 201
    res = staff.client.put(f"/api/v1/parties/{org['id']}/mandate", json={"rule": "a_and_b"}, headers=staff.headers)
    assert res.status_code == 200 and res.get_json()["data"]["rule"] == "a_and_b"

    org = staff.get(f"/api/v1/parties/{org['id']}").get_json()["data"]
    kinds = {(r["relationship"], r["direction"]) for r in org["relationships"]}
    assert kinds == {("director", "incoming"), ("shareholder", "incoming"), ("signatory", "incoming")}
    assert next(r for r in org["relationships"] if r["relationship"] == "shareholder")["share_pct"] == "60.0000"
    assert org["mandate"]["rule"] == "a_and_b"
    assert org["missing_fields"] == [] and org["kyc_status"] == "pending_review"
    # The director is a party too, with the director, shareholder and signatory roles.
    director = staff.get(f"/api/v1/parties/{director_id}").get_json()["data"]
    assert {r["role"] for r in director["roles"]} == {"director", "shareholder", "signatory"}
    assert director["relationships"][0]["direction"] == "outgoing"


def test_kyc_02_rules_on_relationships(staff):
    org = create(staff, company())["data"]
    jane = create(staff, person())["data"]
    res = staff.post(f"/api/v1/parties/{jane['id']}/relationships",
                     {"relationship": "director", "related_party_id": org["id"]})
    assert res.status_code == 400 and "organisation" in res.get_json()["message"]
    res = staff.post(f"/api/v1/parties/{org['id']}/relationships",
                     {"relationship": "shareholder", "related_party_id": jane["id"], "share_pct": "120"})
    assert res.status_code == 400
    res = staff.post(f"/api/v1/parties/{org['id']}/relationships", {"relationship": "director", "related_party_id": org["id"]})
    assert res.status_code == 400
    staff.post(f"/api/v1/parties/{org['id']}/relationships", {"relationship": "director", "related_party_id": jane["id"]})
    res = staff.post(f"/api/v1/parties/{org['id']}/relationships", {"relationship": "director", "related_party_id": jane["id"]})
    assert res.status_code == 409
    res = staff.client.put(f"/api/v1/parties/{org['id']}/mandate", json={"rule": "custom"}, headers=staff.headers)
    assert res.status_code == 400


def test_kyc_03_next_of_kin_and_guarantor_amount(staff):
    jane = create(staff, person())["data"]
    res = staff.post(f"/api/v1/parties/{jane['id']}/relationships", {
        "relationship": "next_of_kin", "kin_relationship": "spouse",
        "related": {"person": {"first_name": "Peter", "last_name": "Doe"},
                    "contacts": [{"kind": "mobile", "value": "0733456120"}, {"kind": "email", "value": "peter@example.com"}],
                    "addresses": [{"kind": "home", "line1": "Hse 4, Riverside Dr"}]}})
    assert res.status_code == 201, res.get_json()
    assert res.get_json()["data"]["kin_relationship"] == "spouse"

    res = staff.post(f"/api/v1/parties/{jane['id']}/relationships", {
        "relationship": "guarantor_of", "committed_amount": "250,000.00",
        "related": {"person": {"first_name": "Mary", "last_name": "Owino"},
                    "identifiers": [{"id_type": "national_id", "value": "33456789"}, {"id_type": "kra_pin", "value": "A018765432Q"}],
                    "contacts": [{"kind": "mobile", "value": "0745667889"}]}})
    assert res.status_code == 201, res.get_json()
    assert res.get_json()["data"]["committed_amount"] == "250000.00"

    jane = staff.get(f"/api/v1/parties/{jane['id']}").get_json()["data"]
    assert jane["missing_fields"] == [] and jane["kyc_status"] == "pending_review"
    rels = {r["relationship"]: r for r in jane["relationships"]}
    assert rels["next_of_kin"]["party"]["display_name"] == "Peter Doe"
    assert rels["guarantor_of"]["party"]["display_name"] == "Mary Owino"
    mary = staff.get(f"/api/v1/parties/{rels['guarantor_of']['party']['id']}").get_json()["data"]
    assert [r["role"] for r in mary["roles"]] == ["guarantor"]

    # A guarantor commits a positive amount with at most 2 decimals; others commit nothing.
    for bad in ("0", "10.555", ""):
        res = staff.post(f"/api/v1/parties/{jane['id']}/relationships",
                         {"relationship": "guarantor_of", "committed_amount": bad,
                          "related": {"person": {"first_name": "X", "last_name": f"Y{bad}"}}})
        assert res.status_code == 400, bad
    res = staff.post(f"/api/v1/parties/{jane['id']}/relationships",
                     {"relationship": "related_party", "committed_amount": "100",
                      "related": {"person": {"first_name": "Z", "last_name": "Z"}}})
    assert res.status_code == 400

    # Ending the next of kin makes KYC incomplete again.
    kin = rels["next_of_kin"]
    assert staff.post(f"/api/v1/parties/{jane['id']}/relationships/{kin['id']}/end").status_code == 200
    jane = staff.get(f"/api/v1/parties/{jane['id']}").get_json()["data"]
    assert jane["kyc_status"] == "incomplete" and jane["missing_fields"] == ["next_of_kin"]


def test_kyc_04_duplicate_id_refused(staff):
    first = create(staff, person())["data"]
    body = person(identifiers=[{"id_type": "national_id", "value": "12-345-678"}],
                  contacts=[], person={"first_name": "Someone", "last_name": "Else"})
    res = create(staff, body, 409)
    assert res["message"] == f"ID number already registered to {first['party_no']} (Jane Wanjiru Doe)."
    assert Party.query.count() == 1


def test_kyc_04_duplicate_kra_pin_refused(staff):
    create(staff, person())
    body = person(identifiers=[{"id_type": "kra_pin", "value": "A 0123-45678 K"}], person={"first_name": "B", "last_name": "C"})
    assert "KRA PIN already registered to P-0000001" in create(staff, body, 409)["message"]


def test_kyc_04_duplicate_company_reg_refused(staff):
    create(staff, company())
    body = company(identifiers=[{"id_type": "company_reg_no", "value": "pvt abc123"}])
    assert "Company registration number already registered to P-0000001 (Acme Traders Ltd)" in create(staff, body, 409)["message"]


def test_kyc_04_duplicate_refused_across_branches(app, staff):
    db.session.add(Branch(id=2, code="001", name="Mombasa", status="active"))
    db.session.commit()
    create(staff, person(home_branch_id=2))
    res = create(staff, person(home_branch_id=1, person={"first_name": "J", "last_name": "D"}), 409)
    assert "already registered to P-0000001" in res["message"]
    # Also when the duplicate arrives as a related party.
    org = create(staff, company())["data"]
    res = staff.post(f"/api/v1/parties/{org['id']}/relationships", {
        "relationship": "director", "related": {"person": {"first_name": "J", "last_name": "D"},
                                                "identifiers": [{"id_type": "national_id", "value": "12345678"}]}})
    assert res.status_code == 409 and "P-0000001" in res.get_json()["message"]


def test_kyc_04_database_refuses_duplicate_identifier(staff):
    create(staff, person())
    other = create(staff, person(identifiers=[], contacts=[], person={"first_name": "B", "last_name": "C"}))["data"]
    with pytest.raises(IntegrityError, match="uq_party_identifiers_value"):
        db.session.execute(text(
            "INSERT INTO party_identifiers (party_id, id_type, issuing_country, value_display, value_normalised) "
            "VALUES (:p, 'national_id', 'KE', '12345678', '12345678')"), {"p": other["id"]})
        db.session.flush()
    db.session.rollback()
    with pytest.raises(Exception, match="never deleted"):
        db.session.execute(text("DELETE FROM parties WHERE id = :p"), {"p": other["id"]})
    db.session.rollback()


def test_kyc_11_party_types(staff):
    for i, org_type in enumerate(("sme", "corporate", "cooperative", "ngo", "investment_group", "public_institution")):
        body = company(organisation={"legal_name": f"Org {i}", "org_type": org_type},
                       identifiers=[{"id_type": "company_reg_no", "value": f"REG{i}"}])
        assert create(staff, body)["data"]["organisation"]["org_type"] == org_type
    assert "org_type" in create(staff, company(organisation={"legal_name": "X", "org_type": "bank"}), 400)["message"]
    res = staff.get("/api/v1/parties?type=organisation").get_json()["data"]
    assert res["total"] == 6
    assert create(staff, company(identifiers=[{"id_type": "national_id", "value": "1"}]), 400)


def test_list_search_and_filters(staff):
    jane = create(staff, person())["data"]
    create(staff, company())
    lst = lambda q: staff.get(f"/api/v1/parties?{q}").get_json()["data"]
    assert lst("")["total"] == 2
    assert [p["party_no"] for p in lst("search=jane")["items"]] == [jane["party_no"]]
    assert lst("search=12345678")["items"][0]["id"] == jane["id"]   # ID number
    assert lst("search=%2B254712345678")["items"][0]["id"] == jane["id"]  # phone in another format
    assert lst("search=P-0000002")["items"][0]["display_name"] == "Acme Traders Ltd"
    assert lst("type=person")["total"] == 1 and lst("kyc_status=incomplete")["total"] == 2
    item = lst("search=jane")["items"][0]
    assert item["phone"] == "0712 345 678" and item["email"] == "Jane@Example.com"


def _complete_person(staff):
    jane = create(staff, person())["data"]
    staff.post(f"/api/v1/parties/{jane['id']}/relationships", {
        "relationship": "next_of_kin", "related": {"person": {"first_name": "Peter", "last_name": "Doe"},
                                                   "contacts": [{"kind": "mobile", "value": "0733456120"}]}})
    return jane


def test_required_fields_block_verification(staff, admin1):
    jane = create(staff, person())["data"]
    res = staff.post(f"/api/v1/parties/{jane['id']}/verify")
    assert res.status_code == 400 and "next of kin" in res.get_json()["message"]


def test_verification_is_maker_checker(staff, admin1, users):
    jane = _complete_person(staff)
    res = staff.post(f"/api/v1/parties/{jane['id']}/verify")
    assert res.status_code == 201, res.get_json()
    cr = res.get_json()["data"]
    assert cr["request_type"] == "party.verify" and cr["entity_id"] == str(jane["id"])
    assert staff.get(f"/api/v1/parties/{jane['id']}").get_json()["data"]["kyc_status"] == "pending_review"
    # Staff can't approve (no kyc.verify); the approver can't be the maker either.
    assert staff.post(f"/api/v1/change-requests/{cr['id']}/approve").status_code == 403
    res = admin1.post(f"/api/v1/change-requests/{cr['id']}/approve")
    assert res.status_code == 200, res.get_json()
    data = staff.get(f"/api/v1/parties/{jane['id']}").get_json()["data"]
    assert data["kyc_status"] == "verified" and data["verified_by"] == "admin1@anchorstone.test"
    assert staff.post(f"/api/v1/parties/{jane['id']}/verify").status_code == 409


def test_maker_cannot_verify_own_request(admin1, admin2):
    jane = _complete_person(admin1)
    cr = admin1.post(f"/api/v1/parties/{jane['id']}/verify").get_json()["data"]
    res = admin1.post(f"/api/v1/change-requests/{cr['id']}/approve")
    assert res.status_code == 403 and "Maker-checker" in res.get_json()["message"]
    assert admin2.post(f"/api/v1/change-requests/{cr['id']}/approve").status_code == 200


def test_database_refuses_verification_decided_by_its_maker(admin1):
    jane = _complete_person(admin1)
    cr = admin1.post(f"/api/v1/parties/{jane['id']}/verify").get_json()["data"]
    maker = db.session.execute(text("SELECT id FROM \"user\" WHERE email = 'admin1@anchorstone.test'")).scalar()
    with pytest.raises(IntegrityError, match="Maker-checker"):
        db.session.execute(text(
            "INSERT INTO change_request_events (request_id, round, action, level, actor_user_id, actor_email, at, "
            "date_created, date_updated) VALUES (:r, 1, 'approve', 1, :u, 'admin1@anchorstone.test', now(), now(), now())"),
            {"r": cr["id"], "u": maker})
        db.session.flush()
    db.session.rollback()


def test_permissions_on_party_routes(client, staff, admin1):
    jane = create(staff, person())["data"]
    # Take party.create away from the staff bundle: staff are refused, admins still allowed.
    role = Role.query.filter_by(legacy_role="user").one()
    db.session.execute(text("DELETE FROM role_permissions WHERE role_id = :r AND permission_code = 'party.create'"),
                       {"r": role.id})
    db.session.commit()
    body = person(identifiers=[], person={"first_name": "N", "last_name": "P"})
    assert staff.post("/api/v1/parties", body).status_code == 403
    assert admin1.post("/api/v1/parties", body).status_code == 201
    assert staff.get(f"/api/v1/parties/{jane['id']}").status_code == 200
    assert client.get("/api/v1/parties").status_code == 401


def test_create_is_audited(staff):
    jane = create(staff, person())["data"]
    row = db.session.execute(text("SELECT action, target_name, user_email FROM audit_logs "
                                  "WHERE action = 'CREATE_PARTY'")).one()
    assert row == ("CREATE_PARTY", jane["party_no"], "staff@anchorstone.test")


def test_phone_numbers_normalised_for_duplicate_checks():
    from app.Parties.normalise import normalise_phone

    assert normalise_phone("0712 345 678") == normalise_phone("+254 712 345 678") == "+254712345678"
    assert normalise_phone("0110 123 456") == "+254110123456"
    assert normalise_phone("020 444 5555") == normalise_phone("254204445555") == "+254204445555"
    assert normalise_phone("712345678") == "+254712345678"
    assert normalise_phone("not a phone") is None and normalise_phone("0012") is None
