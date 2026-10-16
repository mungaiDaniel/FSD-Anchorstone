import uuid

from app.Emails.model import OutboxEmail
from app.Emails.sender import drain_queue, mail
from app.utils.audit_log import AuditLog


def statements():
    return OutboxEmail.query.filter_by(email_type="ACCOUNT_STATEMENT").order_by(OutboxEmail.id).all()


def bulk(api, recipients, key=None):
    return api.post("/api/v1/emails/statements/bulk", {"recipients": recipients, "send_key": key or str(uuid.uuid4())})


# ── Permissions ──


def test_staff_cannot_generate_confirm_or_suppress(staff, admin1, make_investor):
    inv = make_investor()
    assert staff.post(f"/api/v1/investors/{inv['id']}/statement-email").status_code == 403
    assert bulk(staff, {"investor_ids": [inv["id"]]}).status_code == 403
    admin1.post(f"/api/v1/investors/{inv['id']}/statement-email")
    eid = statements()[0].id
    assert staff.post("/api/v1/emails/confirm", {"ids": [eid]}).status_code == 403
    assert staff.post("/api/v1/emails/suppress", {"ids": [eid]}).status_code == 403
    assert statements()[0].status == "pending"


# ── Single investor ──


def test_single_statement_is_pending_with_its_own_pdf_and_never_auto_sent(admin1, make_investor, deposit, rate):
    rate("12", "2026-01-01")
    inv = make_investor(full_name="Grace Wanjiku Mwangi")
    deposit(inv["id"], "250000", "2026-09-01")
    res = admin1.post(f"/api/v1/investors/{inv['id']}/statement-email")
    assert res.status_code == 201
    email = statements()[0]
    assert email.status == "pending"
    assert email.subject.startswith("Your account statement")
    assert "KES 250,000.00" in email.body
    assert email.attachment.data[:4] == b"%PDF"
    assert email.attachment.filename.startswith(f"Anchorstone-statement-{inv['client_code']}")

    # The background sender ignores pending emails.
    with mail.record_messages() as outbox:
        assert drain_queue()["claimed"] == 1  # only the deposit confirmation
    assert all("account statement" not in m.subject for m in outbox)
    assert statements()[0].status == "pending"

    # The stored PDF can be viewed before confirming.
    pdf = admin1.get(f"/api/v1/emails/{email.id}/attachment")
    assert pdf.status_code == 200 and pdf.data[:4] == b"%PDF"
    assert AuditLog.query.filter_by(action="GENERATE_STATEMENT_EMAIL").count() == 1


def test_one_pending_statement_per_investor(admin1, make_investor):
    inv = make_investor()
    assert admin1.post(f"/api/v1/investors/{inv['id']}/statement-email").status_code == 201
    assert admin1.post(f"/api/v1/investors/{inv['id']}/statement-email").status_code == 409
    assert len(statements()) == 1


def test_confirm_sends_it_with_the_stored_pdf(admin1, make_investor):
    inv = make_investor()
    admin1.post(f"/api/v1/investors/{inv['id']}/statement-email")
    email = statements()[0]
    res = admin1.post("/api/v1/emails/confirm", {"ids": [email.id]})
    assert res.status_code == 200 and res.get_json()["data"]["changed"] == 1
    assert statements()[0].status == "queued" and statements()[0].decided_by == "admin1@anchorstone.test"

    with mail.record_messages() as outbox:
        drain_queue()
    msg = next(m for m in outbox if "account statement" in m.subject)
    assert msg.recipients == [inv["email"]]
    assert len(msg.attachments) == 1 and msg.attachments[0].data[:4] == b"%PDF"
    assert statements()[0].status == "sent"
    log = AuditLog.query.filter_by(action="CONFIRM_EMAIL").one()
    assert log.target_id == inv["id"]


def test_suppress_cancels_it_and_it_cannot_be_retried(admin1, make_investor):
    inv = make_investor()
    admin1.post(f"/api/v1/investors/{inv['id']}/statement-email")
    eid = statements()[0].id
    assert admin1.post("/api/v1/emails/suppress", {"ids": [eid]}).get_json()["data"]["changed"] == 1
    assert statements()[0].status == "cancelled"
    assert admin1.post(f"/api/v1/emails/{eid}/retry").status_code == 409
    assert AuditLog.query.filter_by(action="SUPPRESS_EMAIL").count() == 1
    # Suppressing frees the investor for a fresh statement.
    assert admin1.post(f"/api/v1/investors/{inv['id']}/statement-email").status_code == 201


def test_confirm_skips_emails_that_are_not_pending(admin1, make_investor):
    inv = make_investor()
    admin1.post(f"/api/v1/investors/{inv['id']}/statement-email")
    eid = statements()[0].id
    admin1.post("/api/v1/emails/confirm", {"ids": [eid]})
    again = admin1.post("/api/v1/emails/suppress", {"ids": [eid]}).get_json()["data"]
    assert again == {**again, "changed": 0, "skipped": 1}
    assert statements()[0].status == "queued"


# ── Bulk ──


def test_bulk_makes_one_pending_statement_each_with_its_own_figures(admin1, make_investor, deposit):
    a = make_investor(full_name="Aisha Hassan")
    b = make_investor(full_name="Brian Kiprop")
    deposit(a["id"], "1000", "2026-09-01")
    deposit(b["id"], "2000", "2026-09-01")
    res = bulk(admin1, {"investor_ids": [a["id"], b["id"]]})
    assert res.status_code == 201 and res.get_json()["data"]["generated"] == 2
    rows = {e.recipient_name: e for e in statements()}
    assert "KES 1,000.00" in rows["Aisha Hassan"].body and "KES 2,000.00" in rows["Brian Kiprop"].body
    assert rows["Aisha Hassan"].attachment.data != rows["Brian Kiprop"].attachment.data
    assert all(e.status == "pending" for e in rows.values())

    logs = AuditLog.query.filter_by(action="BULK_GENERATE_STATEMENTS").all()
    assert len(logs) == 1 and "2 statement(s)" in logs[0].description
    assert AuditLog.query.filter_by(action="GENERATE_STATEMENT_EMAIL").count() == 0

    # Suppress one, confirm the other: independent.
    admin1.post("/api/v1/emails/suppress", {"ids": [rows["Aisha Hassan"].id]})
    admin1.post("/api/v1/emails/confirm", {"ids": [rows["Brian Kiprop"].id]})
    status = {e.recipient_name: e.status for e in statements()}
    assert status == {"Aisha Hassan": "cancelled", "Brian Kiprop": "queued"}


def test_bulk_select_all_filtered_skips_existing_pending_and_resubmits(admin1, make_investor):
    a = make_investor(full_name="Mary Achieng")
    b = make_investor(full_name="Mary Wanjiru")
    make_investor(full_name="Peter Kamau")
    admin1.post(f"/api/v1/investors/{b['id']}/statement-email")  # already pending
    key = str(uuid.uuid4())
    sel = {"filter": {"search": "mary", "status": "active"}}
    data = bulk(admin1, sel, key).get_json()["data"]
    assert data["generated"] == 1 and data["skipped_pending"] == 1
    assert {e.investor_id for e in statements()} == {a["id"], b["id"]}
    again = bulk(admin1, sel, key)
    assert again.status_code == 200 and again.get_json()["data"]["duplicate"] is True
    assert len(statements()) == 2


def test_overview_counts_pending(admin1, make_investor):
    inv = make_investor()
    admin1.post(f"/api/v1/investors/{inv['id']}/statement-email")
    assert admin1.get("/api/v1/stats/overview").get_json()["data"]["emails"]["pending"] == 1


def test_confirm_all_pending(admin1, make_investor):
    a, b = make_investor(), make_investor()
    bulk(admin1, {"investor_ids": [a["id"], b["id"]]})
    res = admin1.post("/api/v1/emails/confirm", {"all_pending": True})
    assert res.get_json()["data"]["changed"] == 2
    assert {e.status for e in statements()} == {"queued"}
    assert admin1.post("/api/v1/emails/confirm", {"all_pending": True}).status_code == 400
