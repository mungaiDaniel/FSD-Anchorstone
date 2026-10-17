"""Phase 4: chart of accounts (FSD v0.1 FIN-01, WA-13; 03-general-ledger.md §2)."""
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.database.database import db
from app.Ledger.model import GlAccount
from app.utils.audit_log import AuditLog

# Every account the FSD §13.1 posting rules name, by the skeleton's code.
FSD_13_1 = {
    "1101": "Bank", "1110": "M-Pesa clearing", "2100": "Investor deposits", "5100": "Interest expense",
    "2110": "Interest payable to investors", "1200": "Loans receivable", "4300": "Fee income",
    "2810": "Deferred fees", "1210": "Interest receivable", "4100": "Interest income",
    "1211": "Interest in suspense", "1220": "Penalty receivable", "4200": "Penalty income",
    "1290": "Loan loss provision", "5200": "Impairment expense", "4500": "Recoveries income",
}


def _acc(code) -> GlAccount:
    return GlAccount.query.filter_by(code=code).one()


def _submit(api, request_type, payload, expect=201):
    res = api.post("/api/v1/change-requests", {"request_type": request_type, "payload": payload})
    assert res.status_code == expect, res.get_json()
    return res.get_json()["data"] if expect == 201 else res.get_json()


def _approve(api, cr, expect=200):
    res = api.post(f"/api/v1/change-requests/{cr['id']}/approve")
    assert res.status_code == expect, res.get_json()
    return res.get_json()


# ── The seeded skeleton ──


def test_seed_contains_every_fsd_13_1_account_and_is_a_working_assumption(admin1):
    res = admin1.get("/api/v1/gl/accounts")
    assert res.status_code == 200
    rows = {a["code"]: a for a in res.get_json()["data"]}
    for code, what in FSD_13_1.items():
        assert code in rows, f"{what} ({code}) missing"
        assert rows[code]["is_postable"] and rows[code]["is_active"], code
    assert {a["source"] for a in rows.values()} == {"working_assumption"}
    assert all("WA-13" in a["description"] for a in rows.values())
    assert {rows[c]["account_type"] for c in ("1000", "2000", "3000", "4000", "5000")} == \
        {"asset", "liability", "equity", "income", "expense"}


def test_seed_tree_is_consistent():
    accounts = GlAccount.query.all()
    by_id = {a.id: a for a in accounts}
    for a in accounts:
        assert a.currency == "KES"
        if a.parent_id is None:
            assert not a.is_postable, f"{a.code} is a root but takes postings"
            continue
        parent = by_id[a.parent_id]
        assert not parent.is_postable and parent.account_type == a.account_type, a.code
    # Contra accounts carry the opposite normal side.
    assert {_acc(c).normal_side for c in ("1211", "1221", "1290", "1510")} == {"credit"}
    assert _acc("2100").is_control and _acc("2110").is_control and not _acc("1101").is_control


def test_staff_cannot_view_the_chart(staff):
    assert staff.get("/api/v1/gl/accounts").status_code == 403


# ── Maker-checker ──


def test_create_account_needs_a_second_person(admin1, admin2):
    cr = _submit(admin1, "gl.account.create", {"code": "1102", "name": "Bank - payroll account",
                                               "account_type": "asset", "parent_id": _acc("1100").id})
    assert cr["status"] == "pending"
    assert GlAccount.query.filter_by(code="1102").first() is None
    assert _approve(admin1, cr, expect=403)["message"].startswith("Maker-checker")
    assert _approve(admin2, cr)["data"]["status"] == "applied"
    new = _acc("1102")
    assert new.normal_side == "debit" and new.is_postable and new.is_active and new.created_by == "admin1@anchorstone.test"
    assert AuditLog.query.filter_by(action="CHANGE_REQUEST_APPLIED", target_name="gl.account.create").count() == 1


def test_staff_cannot_request_a_chart_change(staff):
    res = _submit(staff, "gl.account.create", {"code": "1102", "name": "X", "account_type": "asset"}, expect=403)
    assert "permission" in res["message"]


@pytest.mark.parametrize("payload, message", [
    ({"code": "1101", "name": "Dup", "account_type": "asset"}, "already used"),
    ({"code": "bad code", "name": "X", "account_type": "asset"}, "letters, digits"),
    ({"code": "1190", "name": "X", "account_type": "cash"}, "account_type must be one of"),
    ({"code": "1190", "name": "", "account_type": "asset"}, "name is required"),
    ({"code": "1190", "name": "X", "account_type": "asset", "parent_id": "1100"}, "parent_id must be"),
    ({"code": "1190", "name": "X", "account_type": "asset", "is_postable": False, "is_control": True},
     "header account can't be a control"),
    ({"code": "1190", "name": "X", "account_type": "asset", "branch_id": 999}, "branch_id must be"),
])
def test_create_refuses_invalid_input(admin1, payload, message):
    res = _submit(admin1, "gl.account.create", payload, expect=400)
    assert message in res["message"], res["message"]


def test_parent_must_be_an_active_header_of_the_same_type(admin1):
    for parent, message in (("1101", "parent must be a header"), ("2000", "type is liability")):
        res = _submit(admin1, "gl.account.create", {"code": "1190", "name": "X", "account_type": "asset",
                                                    "parent_id": _acc(parent).id}, expect=400)
        assert message in res["message"], res["message"]


def test_recode_and_rename_keep_the_same_account(admin1, admin2):
    bank = _acc("1101")
    cr = _submit(admin1, "gl.account.change", {"gl_account_id": bank.id,
                                               "changes": {"code": "1100-01", "name": "Bank - KCB operating"}})
    _approve(admin2, cr)
    db.session.expire_all()
    renamed = db.session.get(GlAccount, bank.id)
    assert (renamed.code, renamed.name, renamed.version) == ("1100-01", "Bank - KCB operating", 2)


def test_change_refuses_a_cycle_and_a_no_op(admin1):
    assets, bank_header = _acc("1000"), _acc("1100")
    res = _submit(admin1, "gl.account.change", {"gl_account_id": assets.id, "changes": {"parent_id": bank_header.id}},
                  expect=400)
    assert "under itself" in res["message"]
    res = _submit(admin1, "gl.account.change", {"gl_account_id": bank_header.id, "changes": {"name": "Bank accounts"}},
                  expect=400)
    assert "Nothing would change" in res["message"]
    res = _submit(admin1, "gl.account.change", {"gl_account_id": bank_header.id, "changes": {"id": 5}}, expect=400)
    assert "can't be changed" in res["message"]


def test_header_with_active_children_cannot_be_deactivated_or_take_postings(admin1):
    header = _acc("1100")
    for changes, message in (({"is_active": False}, "sub-accounts first"),
                             ({"is_postable": True}, "can't take postings"),
                             ({"account_type": "expense", "normal_side": "debit"}, "type is asset")):
        res = _submit(admin1, "gl.account.change", {"gl_account_id": header.id, "changes": changes}, expect=400)
        assert message in res["message"], res["message"]


def test_deactivate_and_reactivate(admin1, admin2):
    cash = _acc("1130")
    _approve(admin2, _submit(admin1, "gl.account.change", {"gl_account_id": cash.id, "changes": {"is_active": False}}))
    db.session.expire_all()
    assert db.session.get(GlAccount, cash.id).is_active is False
    _approve(admin1, _submit(admin2, "gl.account.change", {"gl_account_id": cash.id, "changes": {"is_active": True}}))
    db.session.expire_all()
    assert db.session.get(GlAccount, cash.id).is_active is True


def test_change_fails_if_the_account_changed_after_submit(admin1, admin2, superadmin):
    cash = _acc("1130")
    first = _submit(admin1, "gl.account.change", {"gl_account_id": cash.id, "changes": {"name": "Cash - vault"}})
    second = _submit(admin1, "gl.account.change", {"gl_account_id": cash.id, "changes": {"name": "Cash - till"}})
    _approve(admin2, first)
    assert "changed after this request" in _approve(admin2, second, expect=409)["message"]


# ── Database guarantees ──


def test_database_refuses_to_delete_an_account():
    with pytest.raises(DBAPIError, match="never deleted"):
        db.session.execute(text("DELETE FROM gl_accounts WHERE code = '5500'"))
    db.session.rollback()


@pytest.mark.parametrize("sql, constraint", [
    ("UPDATE gl_accounts SET currency = 'USD' WHERE code = '1101'", "ck_gl_accounts_currency_kes"),
    ("UPDATE gl_accounts SET account_type = 'cash' WHERE code = '1101'", "ck_gl_accounts_type"),
    ("UPDATE gl_accounts SET is_postable = false, is_control = true WHERE code = '2100'",
     "ck_gl_accounts_header_not_control"),
    ("UPDATE gl_accounts SET parent_id = id WHERE code = '1100'", "ck_gl_accounts_not_own_parent"),
    ("UPDATE gl_accounts SET code = 'a b' WHERE code = '1101'", "ck_gl_accounts_code_format"),
])
def test_database_checks_on_accounts(sql, constraint):
    with pytest.raises(IntegrityError, match=constraint):
        db.session.execute(text(sql))
        db.session.flush()
    db.session.rollback()
