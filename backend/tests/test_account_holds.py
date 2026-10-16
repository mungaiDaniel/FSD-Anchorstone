"""
Phase 2b criterion 9: a pending withdrawal reduces the available balance through
an account_holds row (02-domain-model §1.2). Requesting places the hold;
approving or rejecting releases it in the same transaction.
"""
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.database.database import db
from app.Investors.model import Investor
from app.Parties.model import AccountHold
from app.Transactions.ledger import available_balance, pending_withdrawals_total
from app.Transactions.model import Withdrawal
from app.utils.dates import utcnow
from test_investor_migration import migrated_demo_book  # noqa: F401  (fixture)


def _request(api, investor_id, amount):
    return api.post("/api/v1/withdrawals", {"investor_id": investor_id, "amount": str(amount), "method": "mpesa"})


def _holds(investor_id):
    account_id = db.session.get(Investor, investor_id).account_id
    return AccountHold.query.filter_by(account_id=account_id).order_by(AccountHold.id).all()


def _detail(api, investor_id):
    return api.get(f"/api/v1/investors/{investor_id}").get_json()["data"]


def _listed(api, investor_id):
    rows = api.get("/api/v1/investors").get_json()["data"]
    rows = rows["items"] if isinstance(rows, dict) else rows
    return next(r for r in rows if r["id"] == investor_id)


@pytest.fixture
def funded(make_investor, deposit):
    inv = make_investor()
    deposit(inv["id"], "10000", "2026-09-01")
    return inv["id"]


def test_request_places_a_hold_that_reduces_available_balance(staff, users, funded):
    res = _request(staff, funded, "6000.50")
    assert res.status_code == 201
    wid = res.get_json()["data"]["id"]

    [hold] = _holds(funded)
    assert (hold.amount, hold.reason, hold.reference_type, hold.reference_id) == \
        (Decimal("6000.50"), "pending_withdrawal", "withdrawal", wid)
    assert hold.placed_by == users["staff"].email and hold.placed_at is not None
    assert hold.released_at is None and hold.released_by is None

    assert pending_withdrawals_total(funded) == Decimal("6000.50")
    assert available_balance(funded) == Decimal("3999.50")
    assert _detail(staff, funded)["balance"] == "10000.00"  # a hold moves no money
    assert _listed(staff, funded)["pending_withdrawals"] == "6000.50"


def test_approval_releases_the_hold(staff, admin1, users, funded):
    wid = _request(staff, funded, "6000").get_json()["data"]["id"]
    assert admin1.post(f"/api/v1/withdrawals/{wid}/approve").status_code == 200

    [hold] = _holds(funded)
    assert hold.released_by == users["admin1"].email and hold.released_at is not None
    assert pending_withdrawals_total(funded) == 0
    assert available_balance(funded) == Decimal("4000.00")
    assert _listed(staff, funded)["pending_withdrawals"] == "0.00"


def test_rejection_releases_the_hold(staff, admin1, users, funded):
    wid = _request(staff, funded, "6000").get_json()["data"]["id"]
    assert admin1.post(f"/api/v1/withdrawals/{wid}/reject", {"reason": "Investor cancelled"}).status_code == 200

    [hold] = _holds(funded)
    assert hold.released_by == users["admin1"].email
    assert available_balance(funded) == Decimal("10000.00")
    assert _request(staff, funded, "10000").status_code == 201  # the full balance is free again


def test_refused_requests_and_decisions_leave_holds_alone(staff, admin1, funded):
    assert _request(staff, funded, "10000.01").status_code == 400  # over the balance: no hold
    assert _holds(funded) == []

    wid = _request(admin1, funded, "6000").get_json()["data"]["id"]
    assert admin1.post(f"/api/v1/withdrawals/{wid}/approve").status_code == 403    # maker = checker
    assert admin1.post(f"/api/v1/withdrawals/{wid}/reject", {"reason": "x"}).status_code == 403
    assert staff.post(f"/api/v1/withdrawals/{wid}/approve").status_code == 403     # no approval right
    db.session.expire_all()
    [hold] = _holds(funded)
    assert hold.released_at is None

    assert _request(staff, funded, "4000.01").status_code == 400  # 6,000 held → 4,000 available
    assert len(_holds(funded)) == 1


def test_failed_approval_rolls_back_and_keeps_the_hold(staff, admin1, make_investor, deposit):
    inv = make_investor()
    deposit(inv["id"], "10000", "2026-09-10")
    wid = staff.post("/api/v1/withdrawals", {"investor_id": inv["id"], "amount": "5000", "method": "mpesa",
                                             "requested_date": "2026-09-01"}).get_json()["data"]["id"]
    assert admin1.post(f"/api/v1/withdrawals/{wid}/approve", {"value_date": "2026-09-05"}).status_code == 409
    db.session.expire_all()
    [hold] = _holds(inv["id"])
    assert hold.released_at is None
    assert db.session.get(Withdrawal, wid).status == "pending"


def test_other_holds_reduce_available_but_are_not_pending_withdrawals(staff, funded):
    db.session.add(AccountHold(account_id=db.session.get(Investor, funded).account_id, amount=Decimal("7000"),
                               reason="legal", placed_by="compliance@example.com", placed_at=utcnow()))
    db.session.commit()

    assert available_balance(funded) == Decimal("3000.00")
    assert pending_withdrawals_total(funded) == 0
    assert _listed(staff, funded)["pending_withdrawals"] == "0.00"
    assert _request(staff, funded, "3000.01").status_code == 400
    assert _request(staff, funded, "3000").status_code == 201


def _raw(sql, **params):
    db.session.execute(text(sql), params)
    db.session.flush()


@pytest.mark.parametrize("amount", ["0", "-1.00"])
def test_db_refuses_a_hold_that_is_not_positive(funded, amount):
    account_id = db.session.get(Investor, funded).account_id
    with pytest.raises(DBAPIError, match="ck_account_holds_amount_positive"):
        _raw("INSERT INTO account_holds (account_id, amount, reason, placed_by, placed_at) "
             "VALUES (:a, CAST(:amt AS numeric), 'legal', 'x', now())", a=account_id, amt=amount)
    db.session.rollback()


def test_db_refuses_editing_deleting_or_re_releasing_a_hold(staff, admin1, funded):
    wid = _request(staff, funded, "6000").get_json()["data"]["id"]
    hold_id = _holds(funded)[0].id

    for sql, match in [
        ("UPDATE account_holds SET amount = -6000 WHERE id = :i", "can only be released"),
        ("UPDATE account_holds SET amount = 1 WHERE id = :i", "can only be released"),
        ("UPDATE account_holds SET reason = 'legal' WHERE id = :i", "can only be released"),
        ("UPDATE account_holds SET released_at = now() WHERE id = :i", "ck_account_holds_released"),
        ("DELETE FROM account_holds WHERE id = :i", "never deleted"),
        ("INSERT INTO account_holds (account_id, amount, reason, reference_type, reference_id, placed_by, placed_at) "
         "SELECT account_id, amount, reason, reference_type, reference_id, placed_by, placed_at "
         "FROM account_holds WHERE id = :i", "uq_account_holds_reference"),
        ("INSERT INTO account_holds (account_id, amount, reason, placed_by, placed_at) "
         "SELECT account_id, 1, 'whim', 'x', now() FROM account_holds WHERE id = :i", "ck_account_holds_reason"),
    ]:
        with pytest.raises(DBAPIError, match=match):
            _raw(sql, i=hold_id)
        db.session.rollback()

    assert admin1.post(f"/api/v1/withdrawals/{wid}/approve").status_code == 200
    with pytest.raises(DBAPIError, match="already released"):
        _raw("UPDATE account_holds SET released_by = 'someone-else' WHERE id = :i", i=hold_id)
    db.session.rollback()


def test_migration_backfills_a_hold_for_each_pending_withdrawal(migrated_demo_book):
    pending = Withdrawal.query.filter_by(status="pending").all()
    assert pending, "the demo book should include a pending withdrawal"
    holds = AccountHold.query.order_by(AccountHold.reference_id).all()
    assert [(h.reference_type, h.reference_id, h.amount, h.placed_by, h.placed_at, h.released_at) for h in holds] == \
        [("withdrawal", w.id, w.amount, w.requested_by, w.created_at, None) for w in sorted(pending, key=lambda w: w.id)]
    assert all(h.account_id == w.investor.account_id for h, w in zip(holds, sorted(pending, key=lambda w: w.id)))
