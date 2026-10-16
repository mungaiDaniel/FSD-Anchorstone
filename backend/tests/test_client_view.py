"""Phase 2b item 6: the single client view (FSD v0.1 KYC-09)."""
import io

PDF = b"%PDF-1.4\n" + b"x" * 200 + b"\n%%EOF\n"


def test_kyc_09_client_view_lists_accounts_roles_relationships_documents(staff, admin1, make_investor, deposit):
    inv = make_investor(full_name="Jane Doe", id_number="12345678")
    deposit(inv["id"], "100000", "2026-09-01")
    link = staff.get(f"/api/v1/investors/{inv['id']}/party").get_json()["data"]
    party_id = link["party_id"]
    assert link["party_no"] == "P-0000001"

    # Jane directs a company and guarantees a friend.
    org = staff.post("/api/v1/parties", {"party_type": "organisation", "organisation": {"legal_name": "Acme Ltd",
                                                                                      "org_type": "sme"}}).get_json()["data"]
    staff.post(f"/api/v1/parties/{org['id']}/relationships", {"relationship": "director", "related_party_id": party_id})
    friend = staff.post("/api/v1/parties", {"party_type": "person", "person": {"first_name": "Bo", "last_name": "B"},
                                            "roles": ["borrower"]}).get_json()["data"]
    staff.post(f"/api/v1/parties/{friend['id']}/relationships",
               {"relationship": "guarantor_of", "related_party_id": party_id, "committed_amount": "50000"})
    staff.post(f"/api/v1/parties/{party_id}/relationships", {"relationship": "next_of_kin",
                                                            "related": {"person": {"first_name": "Kin", "last_name": "Doe"}}})
    staff.client.post(f"/api/v1/parties/{party_id}/documents", headers=staff.headers, content_type="multipart/form-data",
                      data={"document_type": "national_id", "file": (io.BytesIO(PDF), "id.pdf", "application/pdf")})
    staff.post(f"/api/v1/parties/{party_id}/consents", {"purpose": "kyc_processing", "method": "in_branch"})
    staff.patch(f"/api/v1/parties/{party_id}", {"identifiers": [{"id_type": "national_id", "value": "87654321"}]})

    res = admin1.get(f"/api/v1/parties/{party_id}/overview")
    assert res.status_code == 200
    v = res.get_json()["data"]
    assert v["party_no"] == "P-0000001" and v["display_name"] == "Jane Doe"
    [account] = v["accounts"]
    assert (account["account_no"], account["account_type"], account["balance"], account["investor_id"]) == \
        (inv["client_code"], "investment", "100000.00", inv["id"])
    assert {r["role"] for r in v["roles"]} == {"investor", "director", "guarantor"}
    assert [d["party"]["display_name"] for d in v["directorships"]] == ["Acme Ltd"]
    assert [(g["party"]["display_name"], g["committed_amount"]) for g in v["guarantees"]] == [("Bo B", "50000.00")]
    assert any(r["relationship"] == "next_of_kin" and r["direction"] == "incoming" for r in v["relationships"])
    assert [d["document_type"] for d in v["documents"]] == ["national_id"]
    assert [c["purpose"] for c in v["consents"]] == ["kyc_processing"]
    assert v["screening_results"][0]["trigger"] == "onboarding"
    [pending] = v["pending_changes"]
    assert pending["request_type"] == "party.change" and pending["can_decide"] is True
    assert v["loans"] == []
    # The maker sees the same request but can't decide it.
    assert staff.get(f"/api/v1/parties/{party_id}/overview").get_json()["data"]["pending_changes"][0]["can_decide"] is False
    assert staff.get("/api/v1/parties/999/overview").status_code == 404
