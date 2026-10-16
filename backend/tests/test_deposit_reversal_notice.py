import pytest
from sqlalchemy.exc import IntegrityError

from app.database.database import db
from app.Emails.model import OutboxEmail
from app.Emails.sender import drain_queue, mail


def _reverse(admin, deposit_id, reason="keyed against the wrong investor"):
    return admin.post(f"/api/v1/deposits/{deposit_id}/reverse", {"reason": reason})


def test_reversal_after_confirmation_was_sent_queues_a_notice(app, admin1, make_investor, deposit):
    inv = make_investor(full_name="Jane Wanjiru")
    deposit(inv["id"], "20000", "2026-09-01")
    d = deposit(inv["id"], "5000", "2026-09-02")
    drain_queue()  # both confirmations go out

    res = _reverse(admin1, d["id"])
    assert res.status_code == 200
    assert "reversal notice" in res.get_json()["message"]

    notice = OutboxEmail.query.filter_by(deposit_id=d["id"], email_type="DEPOSIT_REVERSAL").one()
    assert notice.status == "queued" and notice.recipient_email == inv["email"]
    assert "KES 5,000.00" in notice.subject and d["reference"] in notice.subject
    assert "Your account balance is now KES 20,000.00." in notice.body
    assert "keyed against the wrong investor" not in notice.body  # the internal reason stays internal

    with mail.record_messages() as outbox:
        drain_queue()
    assert len(outbox) == 1 and "Deposit Reversed" in outbox[0].html


def test_reversal_before_confirmation_was_sent_just_cancels_it(admin1, make_investor, deposit):
    inv = make_investor()
    d = deposit(inv["id"], "5000", "2026-09-02")
    assert _reverse(admin1, d["id"]).get_json()["message"] == "Deposit reversed."
    emails = OutboxEmail.query.filter_by(deposit_id=d["id"]).all()
    assert [(e.email_type, e.status) for e in emails] == [("DEPOSIT_CONFIRMATION", "cancelled")]


def test_confirmation_being_sent_counts_as_sent(admin1, make_investor, deposit):
    """A confirmation already handed to the mail server can't be recalled, so it gets a notice."""
    inv = make_investor()
    d = deposit(inv["id"], "5000", "2026-09-02")
    OutboxEmail.query.filter_by(deposit_id=d["id"]).update({"status": "sending"})
    db.session.commit()
    _reverse(admin1, d["id"])
    assert OutboxEmail.query.filter_by(deposit_id=d["id"], email_type="DEPOSIT_REVERSAL").count() == 1


def test_failed_confirmation_gets_no_notice(admin1, make_investor, deposit):
    inv = make_investor()
    d = deposit(inv["id"], "5000", "2026-09-02")
    OutboxEmail.query.filter_by(deposit_id=d["id"]).update({"status": "failed"})
    db.session.commit()
    _reverse(admin1, d["id"])
    assert OutboxEmail.query.filter_by(deposit_id=d["id"], email_type="DEPOSIT_REVERSAL").count() == 0


def _notice_row(deposit_id, investor_id):
    return OutboxEmail(email_type="DEPOSIT_REVERSAL", investor_id=investor_id, deposit_id=deposit_id,
                       recipient_email="x@example.com", subject="s", body="b")


def test_database_allows_only_one_reversal_notice_per_deposit(admin1, make_investor, deposit):
    inv = make_investor()
    d = deposit(inv["id"], "5000", "2026-09-02")
    drain_queue()
    _reverse(admin1, d["id"])

    db.session.add(_notice_row(d["id"], inv["id"]))
    with pytest.raises(IntegrityError, match="uq_email_outbox_(deposit_reversal|deposit)"):
        db.session.flush()
    db.session.rollback()


def test_reversal_notice_must_name_its_deposit(make_investor):
    inv = make_investor()
    db.session.add(_notice_row(None, inv["id"]))
    with pytest.raises(IntegrityError, match="ck_email_outbox_reversal_has_deposit"):
        db.session.flush()
    db.session.rollback()
