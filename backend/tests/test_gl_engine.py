"""Phase 4: the posting engine and versioned posting rules (FSD v0.1 §13; 03-general-ledger.md ADR-03-5)."""
import threading
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.database.database import db
from app.Investors.model import Investor
from app.Ledger import engine, rules
from app.Ledger.model import GlAccount, GlEvent, JournalEntry, PostingRule
from app.utils.audit_log import AuditLog, create_audit_log
from app.utils.http import Conflict, ValidationError

ACTOR = "staff@anchorstone.test"


def _id(code) -> int:
    return GlAccount.query.filter_by(code=code).one().id


@pytest.fixture
def account_id(make_investor):
    inv = db.session.get(Investor, make_investor()["id"])
    return inv.account_id


def _deposit(account_id, source_id=1, amount="5000.00", value_date=date(2026, 9, 15), **kw):
    return engine.post("INV_DEPOSIT_POSTED", source=("deposit", source_id), value_date=value_date, branch_id=1,
                       amounts={"amount": amount}, refs={"investment_account": account_id}, actor_email=ACTOR, **kw)


def _lines(entry):
    return [(db.session.get(GlAccount, l.gl_account_id).code, l.debit, l.credit, l.account_id) for l in entry.lines]


# ── Seeded investor rules (03 §4.1, FSD §13.1) ──


def test_seeded_rules_cover_the_investor_events():
    assert {r.event_type for r in rules.current_rules()} == {
        "INV_DEPOSIT_POSTED", "INV_WITHDRAWAL_APPROVED", "INV_INTEREST_APPROVED", "INV_INTEREST_PAID"}
    assert {r.source for r in rules.current_rules()} == {"working_assumption"}


def test_deposit_event_posts_bank_against_the_investor_subledger(account_id):
    entry = _deposit(account_id)
    db.session.commit()
    assert _lines(entry) == [("1101", Decimal("5000.00"), 0, None), ("2100", 0, Decimal("5000.00"), account_id)]
    assert entry.event_type == "INV_DEPOSIT_POSTED" and (entry.source_type, entry.source_id) == ("deposit", "1")
    rule = rules.in_force("INV_DEPOSIT_POSTED", date(2026, 9, 15))
    assert entry.posting_rule_id == rule.id
    event = GlEvent.query.one()
    assert event.journal_entry_id == entry.id and event.amounts == {"amount": "5000.00"}
    assert event.source_key == "INV_DEPOSIT_POSTED:deposit:1:1"


def test_interest_approval_with_tax_and_without(account_id):
    with_tax = engine.post("INV_INTEREST_APPROVED", source=("interest_payout", 1), value_date=date(2026, 9, 30),
                           branch_id=1, amounts={"gross": "1000.00", "tax": "150.00"},
                           refs={"investment_account": account_id}, actor_email=ACTOR)
    no_tax = engine.post("INV_INTEREST_APPROVED", source=("interest_payout", 2), value_date=date(2026, 9, 30),
                         branch_id=1, amounts={"gross": "800.00", "tax": "0"},
                         refs={"investment_account": account_id}, actor_email=ACTOR)
    db.session.commit()
    assert _lines(with_tax) == [("5100", Decimal("1000.00"), 0, None), ("2110", 0, Decimal("1000.00"), account_id),
                                ("2110", Decimal("150.00"), 0, account_id), ("2120", 0, Decimal("150.00"), None)]
    assert [c for c, *_ in _lines(no_tax)] == ["5100", "2110"]  # zero tax leaves out the tax lines
    assert "2100" not in {c for c, *_ in _lines(with_tax)}  # interest never touches investor funds


def test_withdrawal_and_interest_paid(account_id):
    w = engine.post("INV_WITHDRAWAL_APPROVED", source=("withdrawal", 7), value_date=date(2026, 9, 20), branch_id=1,
                    amounts={"amount": "1200.00"}, refs={"investment_account": account_id}, actor_email=ACTOR)
    p = engine.post("INV_INTEREST_PAID", source=("interest_payout", 1), value_date=date(2026, 10, 2), branch_id=1,
                    amounts={"net": "850.00"}, refs={"investment_account": account_id}, actor_email=ACTOR)
    db.session.commit()
    assert _lines(w) == [("2100", Decimal("1200.00"), 0, account_id), ("1101", 0, Decimal("1200.00"), None)]
    assert _lines(p) == [("2110", Decimal("850.00"), 0, account_id), ("1101", 0, Decimal("850.00"), None)]


# ── Idempotency ──


def test_posting_the_same_event_twice_is_refused(account_id):
    first = _deposit(account_id)
    db.session.commit()
    with pytest.raises(Conflict, match=f"already posted as {first.journal_no}"):
        _deposit(account_id)
    db.session.rollback()
    assert JournalEntry.query.count() == 1 and GlEvent.query.count() == 1
    _deposit(account_id, occurrence=2)  # an explicit second occurrence is a different event
    db.session.commit()
    assert GlEvent.query.count() == 2


def test_database_refuses_a_duplicate_source_key(account_id):
    entry = _deposit(account_id)
    db.session.commit()
    event = GlEvent.query.one()
    with pytest.raises(IntegrityError, match="uq_gl_events_source_key"):
        db.session.execute(text(
            "INSERT INTO gl_events (event_type, source_type, source_id, occurrence, value_date, branch_id, amounts,"
            " refs, posting_rule_id, journal_entry_id, created_by) SELECT event_type, source_type, source_id,"
            " occurrence, value_date, branch_id, amounts, refs, posting_rule_id, :j, 'raw' FROM gl_events"),
            {"j": entry.id + 1000})
    db.session.rollback()
    for sql in ("UPDATE gl_events SET amounts = '{}'", "DELETE FROM gl_events"):
        with pytest.raises(DBAPIError, match="never changed or deleted"):
            db.session.execute(text(sql))
        db.session.rollback()
    assert db.session.get(GlEvent, event.id) is not None


def test_concurrent_posts_of_one_event_make_one_journal(app, account_id):
    db.session.commit()
    results, start = {}, threading.Barrier(2)

    def run(key):
        with app.app_context():
            try:
                start.wait(5)
                results[key] = _deposit(account_id).journal_no
                db.session.commit()
            except Exception as e:
                results[key] = e
                db.session.rollback()
            finally:
                db.session.remove()

    threads = [threading.Thread(target=run, args=(k,)) for k in ("a", "b")]
    for t in threads:
        t.start()
    for t in threads:
        t.join(15)
    outcomes = sorted(type(v).__name__ for v in results.values())
    assert outcomes == ["Conflict", "str"], results
    assert JournalEntry.query.count() == 1


# ── The event and its journal commit (or roll back) with the business change ──


def test_event_journal_and_audit_share_the_callers_transaction(account_id):
    _deposit(account_id)
    create_audit_log("POST_DEPOSIT", target_type="deposit", target_id=1, description="test",
                     actor_user_email=ACTOR)
    db.session.rollback()  # e.g. the business change failed
    assert JournalEntry.query.count() == 0 and GlEvent.query.count() == 0
    assert db.session.execute(text("SELECT count(*) FROM journal_lines")).scalar() == 0
    assert AuditLog.query.filter_by(action="POST_DEPOSIT").count() == 0
    _deposit(account_id)  # and the journal number wasn't used up
    db.session.commit()
    assert JournalEntry.query.one().journal_no == "JV-2026-000001"


# ── Refusals ──


@pytest.mark.parametrize("kwargs, message", [
    ({"amounts": {"amount": "10", "fee": "1"}}, "no use for fee"),
    ({"amounts": {}}, "amounts are required"),
    ({"amounts": {"amount": "0"}}, "nothing to post"),
    ({"amounts": {"amount": "1.005"}}, "more than 2 decimal"),
    ({"amounts": {"amount": 10.5}}, "decimal string"),
    ({"refs": {}}, "needs the reference investment_account"),
    ({"value_date": date(2026, 10, 6)}, "future value date"),
    ({"source": ("deposit", None)}, "source must be"),
])
def test_engine_refuses_bad_events(account_id, kwargs, message):
    args = {"source": ("deposit", 1), "value_date": date(2026, 9, 15), "branch_id": 1,
            "amounts": {"amount": "10.00"}, "refs": {"investment_account": account_id}, "actor_email": ACTOR}
    args.update(kwargs)
    with pytest.raises(ValidationError, match=message):
        engine.post("INV_DEPOSIT_POSTED", **args)


def test_unknown_event_type_and_rule_not_yet_in_force(account_id):
    with pytest.raises(ValidationError, match="No posting rule for LOAN_DISBURSED"):
        engine.post("LOAN_DISBURSED", source=("loan", 1), value_date=date(2026, 9, 1), branch_id=1,
                    amounts={"principal": "10"}, actor_email=ACTOR)
    with pytest.raises(ValidationError, match="No posting rule for INV_DEPOSIT_POSTED is in force on 2025-12-31"):
        _deposit(account_id, value_date=date(2025, 12, 31))


# ── Rule versions under maker-checker ──


def _rule_payload(**over):
    payload = {"event_type": "INV_DEPOSIT_POSTED", "effective_from": "2026-10-05",
               "description": "Investor deposit via M-Pesa paybill", "source": "client_confirmed",
               "lines": [{"side": "debit", "gl_account_id": _id("1110"), "amount_field": "amount"},
                         {"side": "credit", "gl_account_id": _id("2100"), "amount_field": "amount",
                          "account_ref": "investment_account"}]}
    payload.update(over)
    return payload


def _submit(api, payload, expect=201):
    res = api.post("/api/v1/change-requests", {"request_type": "gl.posting_rule.change", "payload": payload})
    assert res.status_code == expect, res.get_json()
    return res.get_json()["data"] if expect == 201 else res.get_json()


def test_new_rule_version_applies_from_its_date_and_journals_record_it(admin1, admin2, account_id):
    old = _deposit(account_id, source_id=1, value_date=date(2026, 10, 4))
    db.session.commit()
    cr = _submit(admin1, _rule_payload())
    assert admin1.post(f"/api/v1/change-requests/{cr['id']}/approve").status_code == 403  # maker
    assert admin2.post(f"/api/v1/change-requests/{cr['id']}/approve").status_code == 200
    v2 = rules.latest("INV_DEPOSIT_POSTED")
    assert (v2.version_no, v2.created_by, v2.approved_by) == (2, "admin1@anchorstone.test", "admin2@anchorstone.test")
    earlier = _deposit(account_id, source_id=2, value_date=date(2026, 10, 4))
    today = _deposit(account_id, source_id=3, value_date=date(2026, 10, 5))
    db.session.commit()
    assert _lines(earlier)[0][0] == "1101" and earlier.posting_rule_id == old.posting_rule_id
    assert _lines(today)[0][0] == "1110" and today.posting_rule_id == v2.id
    history = admin1.get("/api/v1/gl/posting-rules?event_type=INV_DEPOSIT_POSTED").get_json()["data"]
    assert [r["version_no"] for r in history] == [2, 1]


@pytest.mark.parametrize("over, message", [
    ({"effective_from": "2026-10-04"}, "can't be in the past"),
    ({"effective_from": "2026-01-01"}, "can't be in the past"),
    ({"lines": [{"side": "debit", "gl_account_id": 1, "amount_field": "amount"}]}, "at least two lines"),
    ({"event_type": "deposit"}, "event_type 'deposit' isn't valid"),
    ("unbalanced", "doesn't balance: amount"),
    ("header", "can't take postings (header)"),
    ("no_ref", "name the account_ref"),
    ("bad_ref", "takes no account_ref"),
    ({"source": "guess"}, "source must be one of"),
])
def test_rule_validation(admin1, over, message):
    payload = _rule_payload()
    if over == "unbalanced":
        payload["lines"].append({"side": "debit", "gl_account_id": _id("1101"), "amount_field": "amount"})
    elif over == "header":
        payload["lines"][0]["gl_account_id"] = _id("1100")
    elif over == "no_ref":
        payload["lines"][1].pop("account_ref")
    elif over == "bad_ref":
        payload["lines"][0]["account_ref"] = "investment_account"
    else:
        payload.update(over)
    assert message in _submit(admin1, payload, expect=400)["message"]


def test_staff_cannot_propose_a_rule(staff):
    assert _submit(staff, _rule_payload(), expect=403)["message"].startswith("You do not have permission")


def test_rule_change_fails_if_another_version_landed_first(admin1, admin2):
    first = _submit(admin1, _rule_payload())
    second = _submit(admin1, _rule_payload(effective_from="2026-11-01"))
    admin2.post(f"/api/v1/change-requests/{first['id']}/approve")
    res = admin2.post(f"/api/v1/change-requests/{second['id']}/approve")
    assert res.status_code == 409 and "changed after this request" in res.get_json()["message"]


def test_rules_are_insert_only_in_the_database(account_id):
    _deposit(account_id)
    db.session.commit()
    rule = rules.in_force("INV_DEPOSIT_POSTED", date(2026, 9, 15))
    for sql in ("UPDATE gl_posting_rules SET description = 'x'", "DELETE FROM gl_posting_rule_lines",
                "UPDATE gl_posting_rule_lines SET side = 'credit'"):
        with pytest.raises(DBAPIError, match="never changed or deleted"):
            db.session.execute(text(sql))
        db.session.rollback()
    with pytest.raises(DBAPIError, match="has been used"):
        db.session.execute(text("INSERT INTO gl_posting_rule_lines (rule_id, line_no, side, gl_account_id,"
                                " amount_field) VALUES (:r, 9, 'debit', :a, 'amount')"), {"r": rule.id, "a": _id("1101")})
    db.session.rollback()
    with pytest.raises(IntegrityError, match="ck_gl_posting_rules_maker_not_checker"):
        db.session.execute(text("INSERT INTO gl_posting_rules (event_type, version_no, effective_from, description,"
                                " source, created_by, approved_by, approved_at) VALUES ('X_TEST', 1, '2026-10-05',"
                                " 'x', 'internal_decision', 'a@x', 'A@X', now())"))
    db.session.rollback()


def test_account_used_by_a_rule_cannot_be_deactivated(admin1):
    res = admin1.post("/api/v1/change-requests", {"request_type": "gl.account.change", "payload": {
        "gl_account_id": _id("2120"), "changes": {"is_active": False}}})
    assert res.status_code == 400 and "posting rule" in res.get_json()["message"]


def test_rule_listing(admin1, staff):
    data = admin1.get("/api/v1/gl/posting-rules").get_json()["data"]
    deposit = next(r for r in data if r["event_type"] == "INV_DEPOSIT_POSTED")
    assert [(l["side"], l["amount_field"], l["account_ref"]) for l in deposit["lines"]] == \
        [("debit", "amount", None), ("credit", "amount", "investment_account")]
    assert admin1.get(f"/api/v1/gl/posting-rules/{deposit['id']}").status_code == 200
    assert staff.get("/api/v1/gl/posting-rules").status_code == 403
    assert PostingRule.query.count() == 4
