"""An action and its audit entry commit together, or not at all."""
import pytest

from app.Emails.model import OutboxEmail
from app.Interest.model import InterestPeriod
from app.Transactions.model import Deposit, Withdrawal
from app.utils.audit_log import AuditLog


@pytest.fixture
def broken_audit(monkeypatch):
    """Make the audit insert itself fail in PostgreSQL: ip_address is
    VARCHAR(45), so a longer value is rejected when the row is flushed."""
    import app.utils.audit_log as audit_log

    real = audit_log.get_client_ip

    def arm(on=True):
        monkeypatch.setattr(audit_log, "get_client_ip", (lambda: "x" * 100) if on else real)

    return arm


def test_deposit_and_its_audit_entry_are_written_together(make_investor, deposit):
    inv = make_investor()
    d = deposit(inv["id"], "1000.00", "2026-09-01")
    entry = AuditLog.query.filter_by(action="RECORD_DEPOSIT").one()
    assert entry.target_id == d["id"]


def test_failed_audit_write_rolls_back_the_deposit(make_investor, staff, broken_audit):
    inv = make_investor()
    broken_audit()
    res = staff.post("/api/v1/deposits", {"investor_id": inv["id"], "amount": "1000.00", "value_date": "2026-09-01",
                                          "method": "bank_transfer", "reference": "REF-ROLLBACK"})
    assert res.status_code == 500
    assert Deposit.query.count() == 0
    assert OutboxEmail.query.count() == 0  # the confirmation email went with it
    assert AuditLog.query.filter_by(action="RECORD_DEPOSIT").count() == 0


def test_failed_audit_write_rolls_back_a_withdrawal_approval(make_investor, deposit, staff, admin1, broken_audit):
    inv = make_investor()
    deposit(inv["id"], "5000.00", "2026-09-01")
    wid = staff.post("/api/v1/withdrawals", {"investor_id": inv["id"], "amount": "1000.00",
                                             "method": "mpesa"}).get_json()["data"]["id"]
    broken_audit()
    assert admin1.post(f"/api/v1/withdrawals/{wid}/approve", {}).status_code == 500
    from app.database.database import db
    w = db.session.get(Withdrawal, wid)
    assert w.status == "pending" and w.value_date is None and w.decided_by is None
    assert OutboxEmail.query.filter_by(withdrawal_id=wid).count() == 0


def test_failed_audit_write_rolls_back_interest_approval(make_investor, deposit, rate, admin1, admin2, broken_audit):
    inv = make_investor()
    rate("12", "2026-01-01")
    deposit(inv["id"], "100000.00", "2026-08-01")
    pid = admin1.post("/api/v1/interest/periods/calculate", {"year": 2026, "month": 8}).get_json()["data"]["id"]
    broken_audit()
    assert admin2.post(f"/api/v1/interest/periods/{pid}/approve").status_code == 500
    from app.database.database import db
    assert db.session.get(InterestPeriod, pid).status == "draft"
    assert OutboxEmail.query.filter_by(email_type="INTEREST_STATEMENT").count() == 0
    # The month isn't locked: a deposit can still be dated into it.
    broken_audit(on=False)
    deposit(inv["id"], "10.00", "2026-08-15")
