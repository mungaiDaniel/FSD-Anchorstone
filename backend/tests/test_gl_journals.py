"""
Phase 4: journals, periods and the rules the database enforces (FSD v0.1 FIN-02,
FIN-03; 03-general-ledger.md ADR-03-2/3). Tests marked "database" bypass the
Python layer with raw SQL and prove PostgreSQL itself refuses the write.
"""
import threading
import time
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.database.database import db
from app.Investors.model import Investor
from app.Ledger import journals, periods
from app.Ledger.model import GlAccount, GlPeriod, JournalEntry, JournalLine
from app.Settings import business
from app.utils.audit_log import AuditLog
from app.utils.http import Conflict, ValidationError
from conftest import Api, _make_user

ACTOR = "admin1@anchorstone.test"


def _id(code) -> int:
    return GlAccount.query.filter_by(code=code).one().id


def _post(value_date=date(2026, 9, 10), amount="1000.00", lines=None, **kw) -> JournalEntry:
    """Dr Bank / Cr Share capital (no subledger needed)."""
    lines = lines or [{"gl_account_id": _id("1101"), "debit": amount},
                      {"gl_account_id": _id("3100"), "credit": amount}]
    return journals.write_entry(value_date=value_date, branch_id=1, description="Test entry", lines=lines,
                                created_by=ACTOR, **kw)


def _close(*labels):
    """Close periods directly (the change-request path is tested separately)."""
    for label in labels:
        period = periods.ensure_period(periods.parse_label(label), ACTOR)
        db.session.execute(text("UPDATE gl_periods SET status = 'closed', closed_by = 'x', closed_at = now() "
                                "WHERE id = :i"), {"i": period.id})
    db.session.commit()


# ── Writing entries ──


def test_entry_is_numbered_per_financial_year_and_stores_its_lines():
    first, second = _post(), _post(amount="250.50")
    db.session.commit()
    assert (first.journal_no, second.journal_no) == ("JV-2026-000001", "JV-2026-000002")
    assert first.entry_date == date(2026, 10, 5) and first.value_date == date(2026, 9, 10)
    assert first.period_id == periods.find(date(2026, 9, 1)).id and first.financial_year == 2026
    assert [(l.debit, l.credit) for l in second.lines] == [(Decimal("250.50"), 0), (0, Decimal("250.50"))]


def test_financial_year_end_comes_from_the_setting_in_force(admin1, admin2):
    res = admin1.post("/api/v1/settings/business/gl.financial_year_end_month",
                      {"value": 6, "effective_from": "2026-10-05", "source": "client_confirmed",
                       "evidence": "Questionnaire G4: year ends 30 June"})
    assert res.status_code == 201, res.get_json()
    assert admin2.post(f"/api/v1/change-requests/{res.get_json()['data']['id']}/approve").status_code == 200
    business.clear_cache()
    october = _post(value_date=date(2026, 10, 2))
    db.session.commit()
    assert october.financial_year == 2027 and october.journal_no == "JV-2027-000001"


@pytest.mark.parametrize("lines, message", [
    ([{"code": "1101", "debit": "10"}], "at least two lines"),
    ([{"code": "1101", "debit": "10"}, {"code": "3100", "credit": "9"}], "doesn't balance"),
    ([{"code": "1101", "debit": "10", "credit": "10"}, {"code": "3100", "credit": "10"}], "exactly one of"),
    ([{"code": "1101", "debit": "-10"}, {"code": "3100", "credit": "-10"}], "can't be negative"),
    ([{"code": "1101", "debit": "10.001"}, {"code": "3100", "credit": "10.001"}], "more than 2 decimal"),
    ([{"code": "1101", "debit": 10.5}, {"code": "3100", "credit": 10.5}], "decimal string"),
    ([{"code": "1100", "debit": "10"}, {"code": "3100", "credit": "10"}], "header account"),
    ([{"code": "5500", "debit": "10"}, {"code": "3100", "credit": "10"}], "inactive"),
    ([{"code": "1101", "debit": "10"}, {"code": "2100", "credit": "10"}], "control account"),
    ([{"code": "1101", "debit": "10", "account_id": 1}, {"code": "3100", "credit": "10"}], "isn't a control"),
])
def test_python_layer_refuses_bad_entries(lines, message):
    built = [{"gl_account_id": _id(l.pop("code")), **l} for l in lines]
    with pytest.raises(ValidationError, match=message):
        _post(lines=built)


def test_control_account_lines_carry_the_client_account(make_investor):
    account_id = Investor.query.get(make_investor()["id"]).account_id
    entry = _post(lines=[{"gl_account_id": _id("1101"), "debit": "500.00"},
                         {"gl_account_id": _id("2100"), "credit": "500.00", "account_id": account_id}])
    db.session.commit()
    assert entry.lines[1].account_id == account_id


def test_posting_into_a_closed_period_is_refused():
    _close("2026-08")
    with pytest.raises(ValidationError, match="2026-08 is closed"):
        _post(value_date=date(2026, 8, 31))
    db.session.rollback()
    with pytest.raises(ValidationError, match="before the latest closed"):
        _post(value_date=date(2026, 7, 1))


# ── Reversals ──


def test_reversal_mirrors_the_original_on_its_value_date():
    original = _post()
    db.session.commit()
    reversal = journals.reverse(original.id, "Posted to the wrong account", ACTOR)
    db.session.commit()
    assert reversal.reversal_of == original.id and reversal.value_date == original.value_date
    assert [(l.gl_account_id, l.debit, l.credit) for l in reversal.lines] == \
        [(l.gl_account_id, l.credit, l.debit) for l in original.lines]
    assert reversal.description.startswith(f"Reversal of {original.journal_no}")


def test_reversal_of_an_entry_in_a_closed_period_is_dated_today():
    original = _post(value_date=date(2026, 8, 20))
    db.session.commit()
    _close("2026-08")
    reversal = journals.reverse(original.id, "Late correction, finance approved", ACTOR)
    db.session.commit()
    assert reversal.value_date == date(2026, 10, 5)


def test_an_entry_is_reversed_once_and_a_reversal_never():
    original = _post()
    db.session.commit()
    with pytest.raises(ValidationError, match="needs a reason"):
        journals.reverse(original.id, "  ", ACTOR)
    reversal = journals.reverse(original.id, "Duplicate", ACTOR)
    db.session.commit()
    with pytest.raises(Conflict, match="already reversed"):
        journals.reverse(original.id, "Again", ACTOR)
    db.session.rollback()
    with pytest.raises(ValidationError, match="itself a reversal"):
        journals.reverse(reversal.id, "Undo the undo", ACTOR)


# ── Database guarantees (raw SQL) ──


def _raw_entry(period_id, value_date="2026-09-10", **extra) -> int:
    cols = {"entry_date": "2026-10-05", "value_date": value_date, "period_id": period_id, "branch_id": 1,
            "description": "raw", "created_by": "raw", "posted_at": "2026-10-05T10:00:00+00:00", **extra}
    names = ", ".join(cols)
    values = ", ".join(f":{k}" for k in cols)
    return db.session.execute(text(f"INSERT INTO journal_entries ({names}, journal_no, financial_year, seq_no,"
                                   f" posted_txid) VALUES ({values}, 'x', 0, 0, 0) RETURNING id"), cols).scalar()


def _raw_line(entry_id, code, debit="0", credit="0", line_no=None, **extra):
    params = {"e": entry_id, "a": _id(code), "d": debit, "c": credit,
              "n": line_no or (db.session.execute(text("SELECT count(*) FROM journal_lines WHERE entry_id = :e"),
                                                  {"e": entry_id}).scalar() + 1),
              "cur": extra.get("currency", "KES"), "acc": extra.get("account_id")}
    db.session.execute(text("INSERT INTO journal_lines (entry_id, line_no, gl_account_id, debit, credit, branch_id,"
                            " currency, account_id) VALUES (:e, :n, :a, :d, :c, 1, :cur, :acc)"), params)


def _period(label="2026-09") -> int:
    period = periods.ensure_period(periods.parse_label(label), ACTOR)
    db.session.commit()
    return period.id


def test_database_rejects_an_unbalanced_entry_at_commit():
    e = _raw_entry(_period())
    _raw_line(e, "1101", debit="100")
    _raw_line(e, "3100", credit="99")
    db.session.flush()  # deferred: the lines are in, nothing has failed yet
    with pytest.raises(IntegrityError, match="unbalanced"):
        db.session.commit()
    db.session.rollback()
    assert JournalEntry.query.count() == 0


@pytest.mark.parametrize("line_count", [0, 1])
def test_database_rejects_an_entry_with_fewer_than_two_lines(line_count):
    e = _raw_entry(_period())
    if line_count:
        _raw_line(e, "1101", debit="100")
    with pytest.raises(IntegrityError, match="at least two lines"):
        db.session.commit()
    db.session.rollback()


def test_database_accepts_a_balanced_entry_and_numbers_it_itself():
    e = _raw_entry(_period())
    _raw_line(e, "1101", debit="100")
    _raw_line(e, "3100", credit="60")
    _raw_line(e, "3200", credit="40")
    db.session.commit()
    entry = db.session.get(JournalEntry, e)
    assert (entry.journal_no, entry.seq_no, entry.financial_year) == ("JV-2026-000001", 1, 2026)


def _committed_entry() -> JournalEntry:
    entry = _post()
    db.session.commit()
    return entry


@pytest.mark.parametrize("sql", [
    "UPDATE journal_entries SET description = 'changed'",
    "UPDATE journal_entries SET value_date = '2026-09-11'",
    "DELETE FROM journal_entries",
    "UPDATE journal_lines SET debit = debit + 1",
    "DELETE FROM journal_lines",
])
def test_database_refuses_to_change_or_delete_posted_journals(sql):
    _committed_entry()
    with pytest.raises(DBAPIError, match="never changed or deleted"):
        db.session.execute(text(sql))
    db.session.rollback()


def test_database_refuses_lines_added_to_an_entry_already_posted():
    entry = _committed_entry()
    with pytest.raises(DBAPIError, match="already posted"):
        _raw_line(entry.id, "1101", debit="5")
        _raw_line(entry.id, "3100", credit="5")
    db.session.rollback()


def test_database_refuses_posting_into_a_closed_period():
    period_id = _period("2026-08")
    _close("2026-08")
    with pytest.raises(IntegrityError, match="2026-08 is closed"):
        _raw_entry(period_id, value_date="2026-08-15")
    db.session.rollback()


def test_database_refuses_an_entry_outside_its_period():
    with pytest.raises(IntegrityError, match="doesn't belong to GL period"):
        _raw_entry(_period("2026-09"), value_date="2026-10-01")
    db.session.rollback()


def test_database_refuses_a_line_in_another_currency():
    e = _raw_entry(_period())
    with pytest.raises(IntegrityError, match="in KES, the line in USD"):
        _raw_line(e, "1101", debit="100", currency="USD")
    db.session.rollback()
    # Beyond the KES check, a line's currency is tied to its entry's by a composite foreign key.
    fk = db.session.execute(text(
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'fk_journal_lines_entry_currency'")).scalar()
    assert fk == "FOREIGN KEY (entry_id, currency) REFERENCES journal_entries(id, currency) ON DELETE RESTRICT"


def test_database_refuses_a_line_with_both_or_neither_side():
    e = _raw_entry(_period())
    for debit, credit in (("10", "10"), ("0", "0"), ("-5", "0")):
        with pytest.raises(IntegrityError, match="ck_journal_lines_one_side"):
            with db.session.begin_nested():
                _raw_line(e, "1101", debit=debit, credit=credit)
    db.session.rollback()


@pytest.mark.parametrize("code, extra, message", [
    ("1100", {}, "is a header"),
    ("5500", {}, "is inactive"),
    ("2100", {}, "is a control account"),
    ("1101", {"account_id": "own"}, "isn't a control account"),
])
def test_database_refuses_lines_on_unusable_accounts(make_investor, code, extra, message):
    if extra.get("account_id") == "own":
        extra["account_id"] = Investor.query.get(make_investor()["id"]).account_id
    e = _raw_entry(_period())
    with pytest.raises(IntegrityError, match=message):
        _raw_line(e, code, debit="10", **extra)
    db.session.rollback()


def test_database_allows_one_reversal_and_never_a_reversal_of_a_reversal():
    original = _committed_entry()
    reversal = journals.reverse(original.id, "Wrong account", ACTOR)
    db.session.commit()
    period_id = _period()
    with pytest.raises(IntegrityError, match="journal_entries_reversal_of_key"):
        _raw_entry(period_id, reversal_of=original.id, reason="again")
    db.session.rollback()
    with pytest.raises(IntegrityError, match="itself a reversal"):
        _raw_entry(period_id, reversal_of=reversal.id, reason="undo")
    db.session.rollback()
    with pytest.raises(IntegrityError, match="ck_journal_entries_reversal_reason"):
        _raw_entry(period_id, reversal_of=original.id)
    db.session.rollback()


def test_database_refuses_an_entry_approved_by_its_maker():
    with pytest.raises(IntegrityError, match="ck_journal_entries_maker_not_checker"):
        _raw_entry(_period(), approved_by="RAW")
    db.session.rollback()


def test_database_guards_periods():
    period_id = _period("2026-08")
    _close("2026-08")
    with pytest.raises(IntegrityError, match="before a closed period"):
        db.session.execute(text("INSERT INTO gl_periods (period_start, period_end, financial_year, status, created_by)"
                                " VALUES ('2026-07-01', '2026-07-31', 2026, 'open', 'raw')"))
    db.session.rollback()
    for sql in ("DELETE FROM gl_periods", "UPDATE gl_periods SET financial_year = 2027"):
        with pytest.raises(DBAPIError, match="never"):
            db.session.execute(text(sql))
        db.session.rollback()
    with pytest.raises(IntegrityError, match="ck_gl_periods_month"):
        db.session.execute(text("INSERT INTO gl_periods (period_start, period_end, financial_year, status, created_by)"
                                " VALUES ('2026-11-02', '2026-11-30', 2026, 'open', 'raw')"))
    db.session.rollback()
    assert db.session.get(GlPeriod, period_id).status == "closed"


def test_database_keeps_the_meaning_of_an_account_with_postings():
    _committed_entry()
    with pytest.raises(DBAPIError, match="has postings"):
        db.session.execute(text("UPDATE gl_accounts SET normal_side = 'credit' WHERE code = '1101'"))
    db.session.rollback()
    with pytest.raises(DBAPIError, match="never deleted"):
        db.session.execute(text("DELETE FROM gl_accounts WHERE code = '1101'"))
    db.session.rollback()
    # Renaming, recoding and deactivating stay possible.
    db.session.execute(text("UPDATE gl_accounts SET code = '1101-A', name = 'Renamed', is_active = false "
                            "WHERE code = '1101'"))
    db.session.commit()


def test_chart_change_is_refused_once_the_account_has_postings(admin1):
    _committed_entry()
    res = admin1.post("/api/v1/change-requests", {"request_type": "gl.account.change", "payload": {
        "gl_account_id": _id("1101"), "changes": {"is_control": True}}})
    assert res.status_code == 400 and "has postings" in res.get_json()["message"]


# ── Gapless numbering under concurrency ──


def _post_in_thread(app, ready, release, results, key, rollback=False):
    with app.app_context():
        try:
            entry = _post()
            results[key] = entry.journal_no
            ready.set()
            release.wait(10)
            db.session.rollback() if rollback else db.session.commit()
        except Exception as e:  # surfaced by the assertions below
            results[key] = e
            ready.set()
        finally:
            db.session.remove()


@pytest.mark.parametrize("first_rolls_back", [False, True])
def test_two_sessions_get_distinct_gapless_numbers(app, first_rolls_back):
    _period()
    ready_a, ready_b, release_a, release_b = (threading.Event() for _ in range(4))
    results = {}
    a = threading.Thread(target=_post_in_thread, args=(app, ready_a, release_a, results, "a", first_rolls_back))
    b = threading.Thread(target=_post_in_thread, args=(app, ready_b, release_b, results, "b"))
    a.start()
    assert ready_a.wait(10)
    b.start()
    time.sleep(0.5)
    assert not ready_b.is_set(), "B must wait for A's sequence lock"
    release_a.set()
    a.join(10)
    assert ready_b.wait(10)
    release_b.set()
    b.join(10)
    assert results["a"] == "JV-2026-000001"
    if first_rolls_back:
        assert results["b"] == "JV-2026-000001"  # the rolled-back number is reused: no gap
    else:
        assert results["b"] == "JV-2026-000002"
    db.session.expire_all()
    seqs = [r[0] for r in db.session.execute(text("SELECT seq_no FROM journal_entries ORDER BY seq_no"))]
    assert seqs == list(range(1, len(seqs) + 1))


# ── Period close and reopen (maker-checker) ──


def _cr(api, request_type, payload, expect=201):
    res = api.post("/api/v1/change-requests", {"request_type": request_type, "payload": payload})
    assert res.status_code == expect, res.get_json()
    return res.get_json()["data"] if expect == 201 else res.get_json()


def test_close_a_period_with_a_second_approver(admin1, admin2):
    _post(value_date=date(2026, 9, 3))
    db.session.commit()
    cr = _cr(admin1, "gl.period.close", {"period": "2026-09"})
    assert admin1.post(f"/api/v1/change-requests/{cr['id']}/approve").status_code == 403
    assert admin2.post(f"/api/v1/change-requests/{cr['id']}/approve").status_code == 200
    db.session.expire_all()
    period = periods.find(date(2026, 9, 1))
    assert period.status == "closed" and period.closed_by == "admin2@anchorstone.test"
    assert AuditLog.query.filter_by(action="CLOSE_GL_PERIOD", target_name="2026-09").count() == 1
    rows = admin1.get("/api/v1/gl/periods").get_json()["data"]
    assert rows[0]["period"] == "2026-09" and rows[0]["status"] == "closed"
    with pytest.raises(ValidationError, match="closed"):
        _post(value_date=date(2026, 9, 30))


def test_close_refusals(admin1, staff):
    assert "permission" in _cr(staff, "gl.period.close", {"period": "2026-09"}, expect=403)["message"]
    assert "hasn't ended" in _cr(admin1, "gl.period.close", {"period": "2026-10"}, expect=400)["message"]
    assert "YYYY-MM" in _cr(admin1, "gl.period.close", {"period": "2026-13"}, expect=400)["message"]
    _post(value_date=date(2026, 8, 3))
    db.session.commit()
    assert "Close 2026-08 first" in _cr(admin1, "gl.period.close", {"period": "2026-09"}, expect=400)["message"]


def test_closing_a_month_without_postings_opens_and_closes_it(admin1, admin2):
    cr = _cr(admin1, "gl.period.close", {"period": "2026-07"})
    assert admin2.post(f"/api/v1/change-requests/{cr['id']}/approve").status_code == 200
    db.session.expire_all()
    assert periods.find(date(2026, 7, 1)).status == "closed"


def test_reopen_needs_a_reason_and_two_super_admins(client, admin1, admin2, superadmin):
    _close("2026-08", "2026-09")
    assert "reason" in _cr(admin1, "gl.period.reopen", {"period": "2026-09", "reason": "x"}, expect=400)["message"]
    assert "latest closed period (2026-09)" in _cr(
        admin1, "gl.period.reopen", {"period": "2026-08", "reason": "Auditor adjustment"}, expect=400)["message"]
    cr = _cr(admin1, "gl.period.reopen", {"period": "2026-09", "reason": "Auditor adjustment to accruals"})
    assert admin2.post(f"/api/v1/change-requests/{cr['id']}/approve").status_code == 403  # not a super admin
    assert superadmin.post(f"/api/v1/change-requests/{cr['id']}/approve").get_json()["data"]["status"] == "pending"
    assert superadmin.post(f"/api/v1/change-requests/{cr['id']}/approve").status_code == 403  # same person twice
    second = Api(client, _make_user("super2@anchorstone.test", "super_admin").email)
    assert second.post(f"/api/v1/change-requests/{cr['id']}/approve").get_json()["data"]["status"] == "applied"
    db.session.expire_all()
    period = periods.find(date(2026, 9, 1))
    assert (period.status, period.reopen_count, period.closed_by) == ("open", 1, None)
    log = AuditLog.query.filter_by(action="REOPEN_GL_PERIOD").one()
    assert "Auditor adjustment" in log.description
    _post(value_date=date(2026, 9, 30))  # posting works again
    db.session.commit()


def test_super_admin_cannot_approve_their_own_reopen(superadmin):
    _close("2026-09")
    cr = _cr(superadmin, "gl.period.reopen", {"period": "2026-09", "reason": "Auditor adjustment"})
    assert superadmin.post(f"/api/v1/change-requests/{cr['id']}/approve").status_code == 403


def test_journal_view(admin1, staff):
    entry = _committed_entry()
    reversal = journals.reverse(entry.id, "Wrong account", ACTOR)
    db.session.commit()
    data = admin1.get(f"/api/v1/gl/journals/{entry.id}").get_json()["data"]
    assert data["journal_no"] == "JV-2026-000001" and data["reversed_by"] == reversal.journal_no
    assert [l["debit"] for l in data["lines"]] == ["1000.00", "0.00"]
    assert staff.get(f"/api/v1/gl/journals/{entry.id}").status_code == 403


def test_only_the_ledger_module_builds_journal_lines():
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1] / "app"
    offenders = [str(p.relative_to(root)) for p in root.rglob("*.py")
                 if p.parent.name != "Ledger" and ("JournalLine(" in p.read_text(encoding="utf-8")
                                                   or "INSERT INTO journal_lines" in p.read_text(encoding="utf-8"))]
    assert offenders == []
