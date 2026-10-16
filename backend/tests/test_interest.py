"""
Expected figures are worked by hand:  Σ(daily closing balance) × rate% / 100 / 365,
rounded half-up to the cent once per investor.
"""
from app.Emails.model import OutboxEmail


def _calc(api, year=2026, month=9):
    return api.post("/api/v1/interest/periods/calculate", {"year": year, "month": month})


def _payouts(api, period_id):
    data = api.get(f"/api/v1/interest/periods/{period_id}").get_json()["data"]
    return {p["client_code"]: p for p in data["payouts"]}, data


def test_daily_balance_interest(staff, admin1, make_investor, deposit, withdraw, rate):
    rate("12", "2026-01-01")
    a, b, c, d = make_investor(), make_investor(), make_investor(), make_investor()

    deposit(a["id"], "100000", "2026-09-01")       # full month: 100,000 × 30 days
    deposit(b["id"], "100000", "2026-09-01")       # 15 days at 100,000 then 15 days at 50,000
    withdraw(b["id"], "50000", "2026-09-16")
    deposit(c["id"], "30000", "2026-09-20")        # 11 days (20th–30th inclusive)
    deposit(d["id"], "5000", "2026-10-01")         # after the period: no September interest

    res = _calc(admin1)
    assert res.status_code == 201, res.get_json()
    payouts, period = _payouts(staff, res.get_json()["data"]["id"])

    assert payouts["ACL-000001"]["gross_interest"] == "986.30"    # 3,000,000 × 0.12 / 365
    assert payouts["ACL-000002"]["gross_interest"] == "739.73"    # 2,250,000 × 0.12 / 365
    assert payouts["ACL-000002"]["closing_balance"] == "50000.00"
    assert payouts["ACL-000002"]["average_daily_balance"] == "75000.00"
    assert payouts["ACL-000003"]["gross_interest"] == "108.49"    # 330,000 × 0.12 / 365
    assert "ACL-000004" not in payouts
    assert period["status"] == "draft"
    assert period["total_gross"] == "1834.52"
    # Tax is modelled but not applied.
    assert all(p["tax_amount"] == "0.00" and p["net_interest"] == p["gross_interest"] for p in payouts.values())


def test_mid_month_rate_change_applies_by_day(staff, admin1, make_investor, deposit, rate):
    rate("12", "2026-01-01")
    rate("15", "2026-09-16")
    inv = make_investor()
    deposit(inv["id"], "100000", "2026-09-01")
    payouts, _ = _payouts(staff, _calc(admin1).get_json()["data"]["id"])
    # 15 days at 12% + 15 days at 15%: (1,500,000×0.12 + 1,500,000×0.15) / 365
    assert payouts["ACL-000001"]["gross_interest"] == "1109.59"
    assert payouts["ACL-000001"]["rate_percent"] == "13.5000"


def test_interest_is_not_added_to_balance(staff, admin1, admin2, make_investor, deposit, rate):
    rate("12", "2026-01-01")
    inv = make_investor()
    deposit(inv["id"], "100000", "2026-09-01")
    pid = _calc(admin1).get_json()["data"]["id"]
    admin2.post(f"/api/v1/interest/periods/{pid}/approve")
    assert staff.get(f"/api/v1/investors/{inv['id']}").get_json()["data"]["balance"] == "100000.00"


def test_calculation_rules(admin1, rate, make_investor, deposit):
    inv = make_investor()
    deposit(inv["id"], "1000", "2026-09-01")
    assert _calc(admin1).status_code == 400                    # no rate in effect
    rate("10", "2026-01-01")
    assert _calc(admin1, 2026, 10).status_code == 400          # October hasn't ended (today is 5 Oct)
    assert _calc(admin1, 2026, 9).status_code == 201
    assert _calc(admin1, 2026, 8).status_code == 409           # one draft at a time
    assert _calc(admin1, 2026, 9).status_code == 201           # recalculating the same draft is fine


def test_approval_is_maker_checker_and_queues_statements(admin1, admin2, make_investor, deposit, rate):
    rate("12", "2026-01-01")
    inv = make_investor()
    deposit(inv["id"], "100000", "2026-09-01")
    pid = _calc(admin1).get_json()["data"]["id"]

    assert admin1.post(f"/api/v1/interest/periods/{pid}/approve").status_code == 403
    res = admin2.post(f"/api/v1/interest/periods/{pid}/approve")
    assert res.status_code == 200
    assert res.get_json()["data"]["status"] == "approved"
    statements = OutboxEmail.query.filter_by(email_type="INTEREST_STATEMENT").all()
    assert len(statements) == 1 and statements[0].investor_id == inv["id"]


def test_stale_draft_cannot_be_approved(admin1, admin2, make_investor, deposit, rate):
    rate("12", "2026-01-01")
    inv = make_investor()
    deposit(inv["id"], "100000", "2026-09-01")
    pid = _calc(admin1).get_json()["data"]["id"]
    deposit(inv["id"], "5000", "2026-09-15")  # backdated into the draft month after calculating
    assert admin2.post(f"/api/v1/interest/periods/{pid}/approve").status_code == 409
    _calc(admin1)
    assert admin2.post(f"/api/v1/interest/periods/{pid}/approve").status_code == 200


def test_approved_month_is_locked(staff, admin1, admin2, make_investor, deposit, rate):
    rate("12", "2026-01-01")
    inv = make_investor()
    deposit(inv["id"], "100000", "2026-08-01")
    pid = _calc(admin1, 2026, 8).get_json()["data"]["id"]
    admin2.post(f"/api/v1/interest/periods/{pid}/approve")

    deposit(inv["id"], "100", "2026-08-31", expect=400)                     # backdated into August
    assert admin1.post("/api/v1/interest/rates", {"rate_percent": "9", "effective_from": "2026-08-15"}).status_code == 400
    assert _calc(admin1, 2026, 8).status_code == 409                       # already approved
    assert _calc(admin1, 2026, 7).status_code == 400                       # must go in order
    assert _calc(admin1, 2026, 9).status_code == 201                       # next month is fine

    wid = staff.post("/api/v1/withdrawals", {"investor_id": inv["id"], "amount": "100", "requested_date": "2026-08-20",
                                             "method": "mpesa"}).get_json()["data"]["id"]
    assert admin1.post(f"/api/v1/withdrawals/{wid}/approve", {"value_date": "2026-08-25"}).status_code == 400


def test_mark_paid_settles_the_period(admin1, admin2, make_investor, deposit, rate):
    rate("12", "2026-01-01")
    a, b = make_investor(), make_investor()
    deposit(a["id"], "100000", "2026-09-01")
    deposit(b["id"], "50000", "2026-09-01")
    pid = _calc(admin1).get_json()["data"]["id"]
    payouts, _ = _payouts(admin1, pid)
    ids = [p["id"] for p in payouts.values()]

    assert admin1.post(f"/api/v1/interest/periods/{pid}/mark-paid",
                       {"payments": [{"payout_id": ids[0], "reference": "X"}]}).status_code == 409  # still draft
    admin2.post(f"/api/v1/interest/periods/{pid}/approve")

    assert admin1.post(f"/api/v1/interest/periods/{pid}/mark-paid",
                       {"payments": [{"payout_id": ids[0]}]}).status_code == 400  # reference required
    res = admin1.post(f"/api/v1/interest/periods/{pid}/mark-paid",
                      {"payments": [{"payout_id": ids[0], "reference": "MPESA1"}]})
    assert res.get_json()["data"]["status"] == "approved"
    res = admin1.post(f"/api/v1/interest/periods/{pid}/mark-paid",
                      {"payments": [{"payout_id": ids[1], "reference": "MPESA2"}]})
    assert res.get_json()["data"]["status"] == "paid"
