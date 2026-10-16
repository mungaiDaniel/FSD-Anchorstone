"""Phase 2b item 7: merging duplicate clients and branch transfers (FSD v0.1 KYC-10, KYC-12)."""
import io

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.Branches.model import Branch
from app.database.database import db
from app.Investors.model import Investor
from app.Parties.model import Account, Party

PDF = b"%PDF-1.4\n" + b"x" * 100 + b"\n%%EOF\n"


def person(api, first, last, ids=(), phone=None, email=None, roles=()):
    res = api.post("/api/v1/parties", {
        "party_type": "person", "person": {"first_name": first, "last_name": last},
        "identifiers": [{"id_type": t, "value": v} for t, v in ids],
        "contacts": ([{"kind": "mobile", "value": phone}] if phone else []) + ([{"kind": "email", "value": email}] if email else []),
        "roles": list(roles)})
    assert res.status_code == 201, res.get_json()
    return res.get_json()["data"]


def submit_merge(api, merged_id, survivor_id, expect=201):
    res = api.post(f"/api/v1/parties/{merged_id}/merge", {"survivor_id": survivor_id,
                                                         "reason": "Same person captured twice at two branches"})
    assert res.status_code == expect, res.get_json()
    return res.get_json()


def test_kyc_10_merge_requires_approval_and_keeps_history(staff, admin1, make_investor):
    # The investor was captured again later as a borrower, with the KRA PIN only.
    inv = make_investor(full_name="Jane Doe", id_number="12345678", email="jane@example.com")
    survivor_id = db.session.get(Investor, inv["id"]).party_id
    dup = person(staff, "Jane", "Doe", ids=[("kra_pin", "A012345678K")], phone="0799000111", roles=["borrower"])
    staff.post(f"/api/v1/parties/{dup['id']}/relationships",
               {"relationship": "next_of_kin", "related": {"person": {"first_name": "Kin", "last_name": "Doe"}}})
    staff.client.post(f"/api/v1/parties/{dup['id']}/documents", headers=staff.headers, content_type="multipart/form-data",
                      data={"document_type": "kra_pin", "file": (io.BytesIO(PDF), "pin.pdf", "application/pdf")})
    staff.post(f"/api/v1/parties/{dup['id']}/consents", {"purpose": "credit_bureau_check", "method": "in_branch"})

    cr = submit_merge(staff, dup["id"], survivor_id)["data"]
    assert cr["request_type"] == "party.merge" and cr["summary"] == f"Merge {dup['party_no']} Jane Doe into P-0000001 Jane Doe"
    assert db.session.get(Party, dup["id"]).status == "active"  # nothing happens before approval
    assert staff.post(f"/api/v1/change-requests/{cr['id']}/approve").status_code == 403
    res = admin1.post(f"/api/v1/change-requests/{cr['id']}/approve")
    assert res.status_code == 200 and res.get_json()["data"]["status"] == "applied"

    db.session.expire_all()
    old = db.session.get(Party, dup["id"])
    assert old.status == "merged" and old.merged_into_party_id == survivor_id
    v = admin1.get(f"/api/v1/parties/{survivor_id}/overview").get_json()["data"]
    assert {i["id_type"] for i in v["identifiers"]} == {"national_id", "kra_pin"}
    assert {r["role"] for r in v["roles"]} == {"investor", "borrower"}
    assert any(r["relationship"] == "next_of_kin" for r in v["relationships"])
    assert [d["document_type"] for d in v["documents"]] == ["kra_pin"]
    assert [c["purpose"] for c in v["consents"]] == ["credit_bureau_check"]
    assert any(c["value"] == "0799000111" for c in v["contacts"])
    assert len(v["screening_results"]) >= 2  # both records' history, plus the re-screen
    # The investor mirror picks up the PIN; the merged record is out of the list but still opens.
    assert staff.get(f"/api/v1/investors/{inv['id']}").get_json()["data"]["kra_pin"] == "A012345678K"
    assert all(p["id"] != dup["id"] for p in staff.get("/api/v1/parties").get_json()["data"]["items"])
    merged_view = staff.get(f"/api/v1/parties/{dup['id']}/overview").get_json()["data"]
    assert merged_view["status"] == "merged" and merged_view["merged_into"]["id"] == survivor_id
    # History: a snapshot of the merged record is in the audit trail.
    row = db.session.execute(text("SELECT old_value FROM audit_logs WHERE action = 'MERGE_PARTY'")).one()
    assert dup["party_no"] in row.old_value and "0799000111" in row.old_value
    # A merged record can't be merged or edited again.
    assert staff.post(f"/api/v1/parties/{dup['id']}/merge", {"survivor_id": survivor_id, "reason": "x"}).status_code == 409


def test_kyc_10_merge_refused_when_both_are_investors(staff, make_investor):
    a = make_investor(full_name="Jane Doe", email="a@example.com")
    b = make_investor(full_name="Jane Doe", email="b@example.com")
    pa, pb = (db.session.get(Investor, i["id"]).party_id for i in (a, b))
    res = submit_merge(staff, pb, pa, expect=409)
    assert "Both" in res["message"] and "investment account" in res["message"]


def test_kyc_10_merge_refused_on_conflicting_identifiers_and_bad_input(staff):
    a = person(staff, "Jane", "Doe", ids=[("national_id", "12345678")])
    b = person(staff, "Jane", "Doe", ids=[("national_id", "87654321")])
    assert "different ID numbers" in submit_merge(staff, b["id"], a["id"], expect=409)["message"]
    assert submit_merge(staff, a["id"], a["id"], expect=400)
    org = staff.post("/api/v1/parties", {"party_type": "organisation",
                                         "organisation": {"legal_name": "Doe Ltd", "org_type": "sme"}}).get_json()["data"]
    assert "organisation" in submit_merge(staff, org["id"], a["id"], expect=400)["message"]
    c = person(staff, "Jane", "Doe", phone="0711000000")
    res = staff.post(f"/api/v1/parties/{c['id']}/merge", {"survivor_id": a["id"]})
    assert res.status_code == 400 and "reason" in res.get_json()["message"]


def test_kyc_10_maker_cannot_approve_merge(admin1, admin2):
    a = person(admin1, "Jane", "Doe")
    b = person(admin1, "Jane", "Doe", phone="0711000000")
    cr = submit_merge(admin1, b["id"], a["id"])["data"]
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
    assert admin2.post(f"/api/v1/change-requests/{cr['id']}/approve").status_code == 200


def test_kyc_10_stale_merge_fails(staff, admin1):
    a = person(staff, "Jane", "Doe")
    b = person(staff, "Jane", "Doe", phone="0711000000")
    cr = submit_merge(staff, b["id"], a["id"])["data"]
    staff.patch(f"/api/v1/parties/{b['id']}", {"contacts": [{"kind": "mobile", "value": "0722999888"}]})
    res = admin1.post(f"/api/v1/change-requests/{cr['id']}/approve")
    assert res.status_code == 409 and "changed after this request" in res.get_json()["message"]


def test_kyc_12_branch_transfer_under_maker_checker(staff, admin1, make_investor):
    db.session.add(Branch(id=2, code="001", name="Mombasa", status="active"))
    db.session.commit()
    inv = make_investor(full_name="Jane Doe")
    party_id = db.session.get(Investor, inv["id"]).party_id
    assert [b["code"] for b in staff.get("/api/v1/branches").get_json()["data"]] == ["000", "001"]

    res = staff.post(f"/api/v1/parties/{party_id}/transfer", {"to_branch_id": 2, "reason": "Client moved to Mombasa"})
    assert res.status_code == 201, res.get_json()
    cr = res.get_json()["data"]
    assert cr["summary"] == "Move P-0000001 Jane Doe to 001 Mombasa"
    assert db.session.get(Party, party_id).home_branch_id == 1
    assert staff.post(f"/api/v1/change-requests/{cr['id']}/approve").status_code == 403
    assert admin1.post(f"/api/v1/change-requests/{cr['id']}/approve").status_code == 200

    db.session.expire_all()
    assert db.session.get(Party, party_id).home_branch_id == 2
    assert db.session.get(Investor, inv["id"]).branch_id == 2
    assert Account.query.filter_by(party_id=party_id).one().branch_id == 2
    # The ACL- code and party number don't change with the branch.
    inv2 = staff.get(f"/api/v1/investors/{inv['id']}").get_json()["data"]
    assert inv2["client_code"] == inv["client_code"] and inv2["branch_id"] == 2
    assert db.session.execute(text("SELECT count(*) FROM audit_logs WHERE action = 'TRANSFER_PARTY_BRANCH'")).scalar() == 1


def test_kyc_12_branch_transfer_refusals(staff):
    p = person(staff, "Jane", "Doe")
    assert staff.post(f"/api/v1/parties/{p['id']}/transfer", {"to_branch_id": 1, "reason": "x"}).status_code == 400
    assert staff.post(f"/api/v1/parties/{p['id']}/transfer", {"to_branch_id": 99, "reason": "x"}).status_code == 400
    db.session.add(Branch(id=3, code="002", name="Closed branch", status="closed"))
    db.session.commit()
    assert staff.post(f"/api/v1/parties/{p['id']}/transfer", {"to_branch_id": 3, "reason": "x"}).status_code == 400
    db.session.add(Branch(id=2, code="001", name="Mombasa", status="active"))
    db.session.commit()
    assert staff.post(f"/api/v1/parties/{p['id']}/transfer", {"to_branch_id": 2}).status_code == 400  # no reason
