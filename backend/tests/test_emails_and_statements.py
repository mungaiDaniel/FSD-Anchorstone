from app.Emails.model import OutboxEmail
from app.Emails.sender import drain_queue, mail


def test_queue_sends_confirmations_and_statement_with_pdf(app, admin1, admin2, make_investor, deposit, rate):
    rate("12", "2026-01-01")
    inv = make_investor(full_name="Jane Wanjiru")
    deposit(inv["id"], "100000", "2026-09-01")
    pid = admin1.post("/api/v1/interest/periods/calculate", {"year": 2026, "month": 9}).get_json()["data"]["id"]
    admin2.post(f"/api/v1/interest/periods/{pid}/approve")

    with mail.record_messages() as outbox:
        result = drain_queue()
    assert result == {"claimed": 2, "sent": 2, "failed": 0}
    assert {e.status for e in OutboxEmail.query.all()} == {"sent"}

    deposit_msg, statement_msg = sorted(outbox, key=lambda m: m.subject)
    assert deposit_msg.recipients == [inv["email"]]
    assert "Anchorstone Capital Ltd" in deposit_msg.html
    assert statement_msg.subject == "Your interest statement — September 2026"
    assert len(statement_msg.attachments) == 1
    assert statement_msg.attachments[0].data[:4] == b"%PDF"

    # Nothing is sent twice.
    assert drain_queue()["claimed"] == 0


def test_no_old_branding_in_outgoing_email(app, make_investor, deposit):
    inv = make_investor()
    deposit(inv["id"], "1000", "2026-09-01")
    with mail.record_messages() as outbox:
        drain_queue()
    text = (outbox[0].html + outbox[0].body).lower()
    for old in ("axys", "ofds", "ofsd", "luminous", "nav", "fund"):
        assert old not in text, old


def test_statement_pdf_endpoint(staff, admin1, admin2, make_investor, deposit, rate):
    rate("12", "2026-01-01")
    inv = make_investor()
    deposit(inv["id"], "100000", "2026-09-01")
    pid = admin1.post("/api/v1/interest/periods/calculate", {"year": 2026, "month": 9}).get_json()["data"]["id"]
    admin2.post(f"/api/v1/interest/periods/{pid}/approve")
    payout_id = staff.get(f"/api/v1/investors/{inv['id']}/payouts").get_json()["data"][0]["id"]

    res = staff.get(f"/api/v1/interest/payouts/{payout_id}/statement.pdf")
    assert res.status_code == 200
    assert res.data[:4] == b"%PDF"


def test_overview_stats(staff, make_investor, deposit):
    inv = make_investor()
    deposit(inv["id"], "1234.56", "2026-10-01")
    data = staff.get("/api/v1/stats/overview").get_json()["data"]
    assert data["total_balance"] == "1234.56"
    assert data["deposits_this_month"] == "1234.56"
    assert data["emails"]["queued"] == 1
