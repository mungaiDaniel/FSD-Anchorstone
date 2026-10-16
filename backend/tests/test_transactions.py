from app.Emails.model import OutboxEmail


def _balance(api, investor_id):
    return api.get(f"/api/v1/investors/{investor_id}").get_json()["data"]["balance"]


def test_investor_gets_sequential_client_code_and_unique_email(staff, make_investor):
    a = make_investor()
    b = make_investor()
    assert a["client_code"] == "ACL-000001"
    assert b["client_code"] == "ACL-000002"
    dup = staff.post("/api/v1/investors", {"full_name": "Dup", "email": a["email"].upper()})
    assert dup.status_code == 409


def test_deposit_updates_balance_and_queues_confirmation(staff, make_investor, deposit):
    inv = make_investor()
    deposit(inv["id"], "100000.00", "2026-09-01")
    deposit(inv["id"], "2500.50", "2026-09-10")
    assert _balance(staff, inv["id"]) == "102500.50"

    emails = OutboxEmail.query.filter_by(investor_id=inv["id"]).all()
    assert [e.email_type for e in emails] == ["DEPOSIT_CONFIRMATION"] * 2
    assert all(e.status == "queued" for e in emails)
    assert "KES 100,000.00" in emails[0].body


def test_deposit_validation(staff, make_investor, deposit):
    inv = make_investor()
    deposit(inv["id"], "100", "2026-10-06", expect=400)       # future date
    deposit(inv["id"], "-5", "2026-09-01", expect=400)        # negative
    deposit(inv["id"], "10.555", "2026-09-01", expect=400)    # sub-cent
    first = deposit(inv["id"], "100", "2026-09-01")
    res = staff.post("/api/v1/deposits", {"investor_id": inv["id"], "amount": "100", "value_date": "2026-09-02",
                                          "method": "mpesa", "reference": first["reference"].lower()})
    assert res.status_code == 409  # same reference, case-insensitive


def test_withdrawal_is_maker_checker(staff, admin1, make_investor, deposit):
    inv = make_investor()
    deposit(inv["id"], "50000", "2026-09-01")

    res = admin1.post("/api/v1/withdrawals", {"investor_id": inv["id"], "amount": "20000", "method": "mpesa"})
    wid = res.get_json()["data"]["id"]
    assert _balance(staff, inv["id"]) == "50000.00"  # pending doesn't move the balance

    own = admin1.post(f"/api/v1/withdrawals/{wid}/approve")
    assert own.status_code == 403  # maker can't approve their own


def test_withdrawal_approval_reduces_balance_and_emails(staff, admin1, make_investor, deposit):
    inv = make_investor()
    deposit(inv["id"], "50000", "2026-09-01")
    wid = staff.post("/api/v1/withdrawals", {"investor_id": inv["id"], "amount": "20000",
                                             "method": "bank_transfer"}).get_json()["data"]["id"]
    res = admin1.post(f"/api/v1/withdrawals/{wid}/approve", {"payment_reference": "TRX-1"})
    assert res.status_code == 200
    assert res.get_json()["data"]["value_date"] == "2026-10-05"  # defaults to today
    assert _balance(staff, inv["id"]) == "30000.00"
    assert OutboxEmail.query.filter_by(withdrawal_id=wid, email_type="WITHDRAWAL_CONFIRMATION").count() == 1

    again = admin1.post(f"/api/v1/withdrawals/{wid}/approve")
    assert again.status_code == 409


def test_withdrawal_cannot_exceed_available_balance(staff, make_investor, deposit):
    inv = make_investor()
    deposit(inv["id"], "10000", "2026-09-01")
    assert staff.post("/api/v1/withdrawals", {"investor_id": inv["id"], "amount": "10000.01",
                                              "method": "mpesa"}).status_code == 400
    assert staff.post("/api/v1/withdrawals", {"investor_id": inv["id"], "amount": "6000",
                                              "method": "mpesa"}).status_code == 201
    # 6,000 already pending -> only 4,000 available
    assert staff.post("/api/v1/withdrawals", {"investor_id": inv["id"], "amount": "4000.01",
                                              "method": "mpesa"}).status_code == 400


def test_backdated_approval_cannot_overdraw_a_later_day(staff, admin1, make_investor, deposit):
    """Deposit on the 10th; a withdrawal can't take effect on the 5th, before the money arrived."""
    inv = make_investor()
    deposit(inv["id"], "10000", "2026-09-10")
    wid = staff.post("/api/v1/withdrawals", {"investor_id": inv["id"], "amount": "5000", "requested_date": "2026-09-01",
                                             "method": "mpesa"}).get_json()["data"]["id"]
    assert admin1.post(f"/api/v1/withdrawals/{wid}/approve", {"value_date": "2026-09-05"}).status_code == 409
    assert admin1.post(f"/api/v1/withdrawals/{wid}/approve", {"value_date": "2026-09-10"}).status_code == 200


def test_reject_requires_reason_and_other_person(staff, admin1, make_investor, deposit):
    inv = make_investor()
    deposit(inv["id"], "1000", "2026-09-01")
    wid = staff.post("/api/v1/withdrawals", {"investor_id": inv["id"], "amount": "500",
                                             "method": "mpesa"}).get_json()["data"]["id"]
    assert admin1.post(f"/api/v1/withdrawals/{wid}/reject").status_code == 400
    res = admin1.post(f"/api/v1/withdrawals/{wid}/reject", {"reason": "Investor cancelled"})
    assert res.status_code == 200
    assert res.get_json()["data"]["status"] == "rejected"
    assert _balance(staff, inv["id"]) == "1000.00"


def test_deposit_reversal(staff, admin1, make_investor, deposit, withdraw):
    inv = make_investor()
    d1 = deposit(inv["id"], "10000", "2026-09-01")
    d2 = deposit(inv["id"], "5000", "2026-09-02")
    withdraw(inv["id"], "12000", "2026-09-03")

    # Reversing d1 would leave the account negative because the withdrawal used it.
    assert admin1.post(f"/api/v1/deposits/{d1['id']}/reverse", {"reason": "duplicate"}).status_code == 409
    assert admin1.post(f"/api/v1/deposits/{d2['id']}/reverse").status_code == 400  # reason required

    d3 = deposit(inv["id"], "700", "2026-09-04")
    res = admin1.post(f"/api/v1/deposits/{d3['id']}/reverse", {"reason": "keyed wrong account"})
    assert res.status_code == 200
    assert _balance(staff, inv["id"]) == "3000.00"
    # Its confirmation email hadn't been sent yet, so it's cancelled.
    assert OutboxEmail.query.filter_by(deposit_id=d3["id"]).one().status == "cancelled"


def test_closing_an_account_requires_zero_balance(staff, admin1, make_investor, deposit, withdraw):
    inv = make_investor()
    deposit(inv["id"], "1000", "2026-09-01")
    assert staff.patch(f"/api/v1/investors/{inv['id']}/status", {"status": "closed"}).status_code == 403
    assert admin1.patch(f"/api/v1/investors/{inv['id']}/status", {"status": "closed"}).status_code == 409
    withdraw(inv["id"], "1000", "2026-09-02")
    assert admin1.patch(f"/api/v1/investors/{inv['id']}/status", {"status": "closed"}).status_code == 200
    deposit(inv["id"], "10", "2026-09-03", expect=400)
