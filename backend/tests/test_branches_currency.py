"""Phase 2a item 1: one Head Office branch, and every money row is KES."""
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.Branches.model import HEAD_OFFICE_ID, Branch
from app.database.database import db
from app.Interest.model import InterestPayout, InterestPeriod
from app.Investors.model import Investor
from app.Transactions.model import Deposit, Withdrawal

MONEY_TABLES = ("deposits", "withdrawals", "interest_periods", "interest_payouts")


def test_head_office_is_seeded():
    branches = Branch.query.all()
    assert [(b.id, b.code, b.name, b.status) for b in branches] == [(HEAD_OFFICE_ID, "000", "Head Office", "active")]


def test_rows_without_branch_or_currency_default_to_head_office_and_kes(make_investor):
    # The migration fills existing rows through these same column defaults.
    inv = make_investor()
    db.session.execute(text(
        "INSERT INTO deposits (investor_id, amount, value_date, method, reference, status, recorded_by, created_at,"
        " date_created, date_updated) VALUES (:i, 100, '2026-09-01', 'cash', 'RAW1', 'posted', 'x', now(), now(), now())"
    ), {"i": inv["id"]})
    db.session.commit()
    row = db.session.execute(text("SELECT currency, branch_id FROM deposits WHERE reference = 'RAW1'")).one()
    assert tuple(row) == ("KES", HEAD_OFFICE_ID)
    assert db.session.get(Investor, inv["id"]).branch_id == HEAD_OFFICE_ID


def test_new_money_rows_inherit_the_investor_branch_and_are_kes(make_investor, deposit, withdraw, rate, admin1, admin2):
    inv = make_investor()
    rate("12", "2026-01-01")
    deposit(inv["id"], "100000", "2026-08-01")
    withdraw(inv["id"], "1000", "2026-08-10")
    res = admin1.post("/api/v1/interest/periods/calculate", {"year": 2026, "month": 8})
    assert res.status_code in (200, 201), res.get_json()

    d = Deposit.query.one()
    w = Withdrawal.query.one()
    p = InterestPayout.query.one()
    assert (d.branch_id, d.currency) == (HEAD_OFFICE_ID, "KES")
    assert (w.branch_id, w.currency) == (HEAD_OFFICE_ID, "KES")
    assert (p.branch_id, p.currency) == (HEAD_OFFICE_ID, "KES")
    assert InterestPeriod.query.one().currency == "KES"
    assert res.get_json()["data"]["currency"] == "KES"


@pytest.mark.parametrize("table", MONEY_TABLES)
def test_database_refuses_any_currency_but_kes(table, make_investor, deposit, withdraw, rate, admin1):
    inv = make_investor()
    rate("12", "2026-01-01")
    deposit(inv["id"], "100000", "2026-08-01")
    withdraw(inv["id"], "1000", "2026-08-10")
    assert admin1.post("/api/v1/interest/periods/calculate", {"year": 2026, "month": 8}).status_code in (200, 201)
    with pytest.raises(IntegrityError, match=f"ck_{table}_currency_kes"):
        db.session.execute(text(f"UPDATE {table} SET currency = 'USD'"))
        db.session.flush()
    db.session.rollback()


def test_a_branch_in_use_cannot_be_deleted(make_investor):
    make_investor()
    with pytest.raises(IntegrityError):
        db.session.execute(text("DELETE FROM branches WHERE id = :id"), {"id": HEAD_OFFICE_ID})
        db.session.flush()
    db.session.rollback()


def test_branch_code_must_be_three_digits():
    with pytest.raises(IntegrityError, match="ck_branches_code_format"):
        db.session.add(Branch(code="HQ", name="Bad"))
        db.session.flush()
    db.session.rollback()
