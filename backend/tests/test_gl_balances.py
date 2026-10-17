"""Phase 4: GL balances, trial balance and account statement (FSD v0.1 FIN-08; 03 ADR-03-4)."""
import pathlib
import re
from datetime import date
from decimal import Decimal

import pytest

from app.Branches.model import Branch
from app.database.database import db
from app.Investors.model import Investor
from app.Ledger import balances, engine, journals
from app.Ledger.model import GlAccount

ACTOR = "staff@anchorstone.test"


def _id(code) -> int:
    return GlAccount.query.filter_by(code=code).one().id


@pytest.fixture
def ledger(make_investor):
    """Two investors; deposits, a withdrawal, interest with tax, a payout and a reversed deposit, in Sep–Oct 2026."""
    a = db.session.get(Investor, make_investor()["id"]).account_id
    b = db.session.get(Investor, make_investor()["id"]).account_id
    db.session.add(Branch(code="001", name="Nakuru", status="active"))
    db.session.commit()

    def post(event, sid, d, amounts, acct, branch=1):
        return engine.post(event, source=("test", sid), value_date=d, branch_id=branch, amounts=amounts,
                           refs={"investment_account": acct}, actor_email=ACTOR)

    post("INV_DEPOSIT_POSTED", 1, date(2026, 9, 1), {"amount": "100000.00"}, a)
    post("INV_DEPOSIT_POSTED", 2, date(2026, 9, 10), {"amount": "50000.00"}, b, branch=2)
    post("INV_WITHDRAWAL_APPROVED", 3, date(2026, 9, 20), {"amount": "20000.00"}, a)
    post("INV_INTEREST_APPROVED", 4, date(2026, 9, 30), {"gross": "1000.00", "tax": "150.00"}, a)
    post("INV_INTEREST_PAID", 5, date(2026, 10, 2), {"net": "850.00"}, a)
    wrong = post("INV_DEPOSIT_POSTED", 6, date(2026, 9, 15), {"amount": "7000.00"}, b)
    journals.reverse(wrong.id, "Keyed against the wrong investor", ACTOR)
    db.session.commit()
    return {"a": a, "b": b}


def test_account_balances_by_date(ledger):
    bank, funds = _id("1101"), _id("2100")
    assert balances.account_balance(bank, date(2026, 8, 31)) == 0
    assert balances.account_balance(bank, date(2026, 9, 30)) == Decimal("130000.00")
    assert balances.account_balance(bank, date(2026, 10, 5)) == Decimal("129150.00")
    assert balances.account_balance(funds, date(2026, 9, 30)) == Decimal("130000.00")  # credit-normal, positive
    assert balances.account_balance(_id("2110"), date(2026, 10, 5)) == 0                 # accrued then paid
    assert balances.account_balance(_id("2120"), date(2026, 10, 5)) == Decimal("150.00")
    assert balances.account_balance(_id("5100"), date(2026, 10, 5)) == Decimal("1000.00")


def test_balance_by_branch_and_header_rollup(ledger):
    bank = _id("1101")
    assert balances.account_balance(bank, date(2026, 10, 5), branch_id=1) == Decimal("79150.00")
    assert balances.account_balance(bank, date(2026, 10, 5), branch_id=2) == Decimal("50000.00")
    assert balances.account_balance(_id("1100"), date(2026, 10, 5)) == Decimal("129150.00")   # bank header
    assert balances.account_balance(_id("1000"), date(2026, 10, 5)) == Decimal("129150.00")   # all assets
    assert balances.account_balance(_id("1000"), date(2026, 10, 5), include_children=False) == 0


def test_subledger_balances_add_up_to_the_control_account(ledger):
    funds, as_of = _id("2100"), date(2026, 10, 5)
    a, b = (balances.subledger_balance(funds, ledger[k], as_of) for k in ("a", "b"))
    assert (a, b) == (Decimal("80000.00"), Decimal("50000.00"))
    assert a + b == balances.account_balance(funds, as_of)


def test_trial_balance_balances_overall_and_per_branch(ledger):
    tb = balances.trial_balance(date(2026, 10, 5))
    assert tb["balanced"] and tb["total_debit"] == tb["total_credit"] == "130150.00"
    rows = {r["code"]: r for r in tb["rows"]}
    assert (rows["1101"]["debit"], rows["1101"]["credit"]) == ("129150.00", "0.00")
    assert (rows["2100"]["debit"], rows["2100"]["credit"]) == ("0.00", "130000.00")
    assert rows["2110"]["debit"] == rows["2110"]["credit"] == "0.00"
    for branch in (1, 2):
        assert balances.trial_balance(date(2026, 10, 5), branch)["balanced"]
    earlier = balances.trial_balance(date(2026, 9, 9))
    assert [r["code"] for r in earlier["rows"]] == ["1101", "2100"] and earlier["total_debit"] == "100000.00"


def test_account_statement_with_running_balance(ledger):
    st = balances.account_statement(_id("1101"), date(2026, 9, 10), date(2026, 10, 5))
    assert st["opening_balance"] == "100000.00"
    assert [(l["value_date"], l["debit"], l["credit"], l["balance"]) for l in st["lines"]] == [
        ("2026-09-10", "50000.00", "0.00", "150000.00"),
        ("2026-09-15", "7000.00", "0.00", "157000.00"),
        ("2026-09-15", "0.00", "7000.00", "150000.00"),       # the reversal, on the original's date
        ("2026-09-20", "0.00", "20000.00", "130000.00"),
        ("2026-10-02", "0.00", "850.00", "129150.00"),
    ]
    assert st["closing_balance"] == "129150.00"
    assert st["total_debit"] == "57000.00" and st["total_credit"] == "27850.00"
    assert all(l["journal_no"].startswith("JV-2026-") for l in st["lines"])


def test_query_routes(admin1, staff, ledger):
    bank = _id("1101")
    tb = admin1.get("/api/v1/gl/trial-balance?as_of=2026-10-05").get_json()["data"]
    assert tb["balanced"] is True
    assert admin1.get("/api/v1/gl/trial-balance?branch_id=2").get_json()["data"]["total_debit"] == "50000.00"
    res = admin1.get(f"/api/v1/gl/accounts/{bank}/balance?as_of=2026-09-30").get_json()["data"]
    assert res["balance"] == "130000.00"
    st = admin1.get(f"/api/v1/gl/accounts/{bank}/statement?from=2026-10-01&to=2026-10-05").get_json()["data"]
    assert st["opening_balance"] == "130000.00" and len(st["lines"]) == 1
    default = admin1.get(f"/api/v1/gl/accounts/{bank}/statement").get_json()["data"]
    assert (default["from"], default["to"]) == ("2026-10-01", "2026-10-05")
    assert admin1.get(f"/api/v1/gl/accounts/{bank}/statement?from=2026-10-05&to=2026-10-01").status_code == 400
    assert admin1.get("/api/v1/gl/trial-balance?branch_id=x").status_code == 400
    assert admin1.get("/api/v1/gl/accounts/99999/balance").status_code == 404
    for url in ("/api/v1/gl/trial-balance", f"/api/v1/gl/accounts/{bank}/balance",
                f"/api/v1/gl/accounts/{bank}/statement"):
        assert staff.get(url).status_code == 403


def test_only_the_balances_module_sums_journal_lines():
    root = pathlib.Path(__file__).resolve().parents[1] / "app"
    pattern = re.compile(r"func\.sum\(\s*JournalLine|sum\(\s*(jl\.)?(debit|credit)\b.*journal_lines", re.I | re.S)
    offenders = [str(p.relative_to(root)) for p in root.rglob("*.py")
                 if p.name != "balances.py" and pattern.search(p.read_text(encoding="utf-8"))]
    assert offenders == []
