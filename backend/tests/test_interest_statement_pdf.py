"""Interest statement PDFs are generated and stored when the month is approved."""
import base64
import re
import zlib

from app.database.database import db
from app.Emails.model import OutboxEmail
from app.Emails.sender import drain_queue, mail
from app.utils.pdf_generator import generate_interest_statement_pdf


def pdf_text(pdf: bytes) -> str:
    """Text drawn on the pages. ReportLab writes page content as (...) Tj
    operators in streams encoded ASCII85 then Flate."""
    out = []
    for raw in re.findall(rb"stream\r?\n(.*?)~>\s*endstream", pdf, re.S):
        try:
            raw = zlib.decompress(base64.a85decode(raw, adobe=False, ignorechars=b" \t\r\n"))
        except (ValueError, zlib.error):
            continue
        out += [m.decode("latin-1") for m in re.findall(rb"\((.*?)\)\s*Tj", raw)]
    return " ".join(out)


def approve_september(admin1, admin2, make_investor, deposit, rate):
    rate("12", "2026-01-01")
    inv = make_investor(full_name="Jane Wanjiru", payout_account="0711111111")
    deposit(inv["id"], "100000", "2026-09-01")
    pid = admin1.post("/api/v1/interest/periods/calculate", {"year": 2026, "month": 9}).get_json()["data"]["id"]
    assert admin2.post(f"/api/v1/interest/periods/{pid}/approve").status_code == 200
    email = OutboxEmail.query.filter_by(email_type="INTEREST_STATEMENT").one()
    return inv, email


def test_pdf_is_stored_at_approval(admin1, admin2, make_investor, deposit, rate):
    inv, email = approve_september(admin1, admin2, make_investor, deposit, rate)
    assert email.status == "queued"
    assert email.attachment is not None and email.attachment.data[:4] == b"%PDF"
    assert email.attachment.filename == "Anchorstone-statement-ACL-000001-2026-09.pdf"
    assert "Jane Wanjiru" in pdf_text(email.attachment.data)


def test_changes_after_approval_do_not_change_the_issued_pdf(staff, admin1, admin2, make_investor, deposit, rate):
    inv, email = approve_september(admin1, admin2, make_investor, deposit, rate)
    stored = email.attachment.data

    # The investor's details change after the statement was issued.
    res = staff.patch(f"/api/v1/investors/{inv['id']}", {"full_name": "Jane Wanjiru-Otieno",
                                                           "payout_account": "0799999999"})
    assert res.status_code == 200

    # Generating now would give a different statement...
    live = pdf_text(generate_interest_statement_pdf(email.payout_id))
    assert "Jane Wanjiru-Otieno" in live
    # ...but the stored one is untouched,
    db.session.expire_all()
    email = db.session.get(OutboxEmail, email.id)
    assert email.attachment.data == stored
    assert "Jane Wanjiru-Otieno" not in pdf_text(stored)

    # the investor is sent exactly that file,
    with mail.record_messages() as outbox:
        drain_queue()
    statement = next(m for m in outbox if m.subject.startswith("Your interest statement"))
    assert len(statement.attachments) == 1
    assert statement.attachments[0].data == stored
    assert statement.attachments[0].filename == "Anchorstone-statement-ACL-000001-2026-09.pdf"

    # and staff see the same file as issued.
    res = staff.get(f"/api/v1/interest/payouts/{email.payout_id}/statement.pdf")
    assert res.status_code == 200 and res.data == stored
