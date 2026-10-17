"""Phase 3a: bank and M-Pesa statements are read page by page; Python checks every page and
computes the metrics (05 §6). Recorded responses only; see test_docai.py for the set-up.

Hand calculations used below (tests/fixtures/make_fixtures.py has the sample statements):

Bank statement, 01/07/2026–30/09/2026, three pages:
    p1  50,000.00 + 85,000.00 − 19,000.00 = 116,000.00
    p2 116,000.00 + 80,000.00 − 41,250.50 = 154,749.50   (the misread answer has 40,250.50 → 155,749.50)
    p3 154,749.50 + 80,000.00 − 28,000.00 = 206,749.50
    credits 245,000.00 over 3 months → 81,666.67 a month; credits in all 3 months → 1.0000
    returned: "CHQ 000123 RTD INSUFF FUNDS" 5,000.00
    lenders: FULIZA REPAYMENT 2,500 + TALA LOAN REPAYMENT 4,000 + FULIZA M-PESA REPAYMENT 3,000
             = 9,500.00 → 3,166.67 a month
M-Pesa statement, 01/08/2026–30/09/2026, newest first, no printed page balances:
    p1 (September) 13,800.00 + 20,500.00 − 8,500.00 = 25,800.00
    p2 (August)     3,000.00 + 15,000.00 − 4,200.00 = 13,800.00
    credits 35,500.00 over 2 months → 17,750.00; lenders M-Shwari 3,500 + Fuliza 1,200 = 4,700.00 → 2,350.00
"""
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.database.database import db
from app.DocAI import metrics
from app.DocAI.model import StatementMetric, StatementMetricInput, StatementPage, StatementTransaction
from app.DocAI.statements import Row, check_page
from docai_fakes import api_error, recorded, response
from test_docai import ai, calls, client_with, fields, read  # noqa: F401 (ai is a fixture)

BANK = ("bank_statement_3_pages.pdf", "application/pdf")
MPESA = ("mpesa_statement_2_pages.pdf", "application/pdf")


def pages(ex):
    return {p.page_number: p for p in StatementPage.query.filter_by(extraction_id=ex.id)}


def txns(ex):
    return (StatementTransaction.query.filter_by(extraction_id=ex.id)
            .order_by(StatementTransaction.page_number, StatementTransaction.row_no).all())


def metric_values(ex):
    return {m.metric: m.value for m in StatementMetric.query.filter_by(extraction_id=ex.id)}


def inputs(ex, metric):
    m = StatementMetric.query.filter_by(extraction_id=ex.id, metric=metric).one()
    ids = [i.transaction_id for i in StatementMetricInput.query.filter_by(metric_id=m.id)]
    return sorted(t.description for t in StatementTransaction.query.filter(StatementTransaction.id.in_(ids)))


def test_bank_statement_with_a_misread_amount_flags_that_page_for_review(ai, staff, users):
    p, doc = client_with(staff, "bank_statement", BANK)
    ex = read(users, p, doc, ai, response("bank_statement_page1"), response("bank_statement_page2_misread"),
              response("bank_statement_page3"))
    assert ex.status == "needs_review" and ex.page_count == 3
    assert "Page(s) 2 don't add up" in ex.status_reason and "no figures were worked out" in ex.status_reason
    got = pages(ex)
    assert [got[n].status for n in (1, 2, 3)] == ["balanced", "needs_review", "balanced"]
    p2 = got[2]
    assert (p2.opening_balance, p2.credits_total, p2.debits_total) == \
        (Decimal("116000.00"), Decimal("80000.00"), Decimal("40250.50"))
    assert (p2.computed_closing, p2.closing_balance, p2.difference) == \
        (Decimal("155749.50"), Decimal("154749.50"), Decimal("1000.00"))
    assert "difference KES 1,000.00" in p2.reason and "row(s) 4" in p2.reason
    assert (got[1].computed_closing, got[3].computed_closing) == (Decimal("116000.00"), Decimal("206749.50"))
    assert len(txns(ex)) == 13 and metric_values(ex) == {}  # no metrics from a statement that doesn't balance
    # One call per page, each with only that page.
    assert [c.page_number for c in calls(ex)] == [1, 2, 3]
    for n, sent in enumerate(ai.calls, 1):
        block, intro = sent["messages"][0]["content"]
        assert block["type"] == "document" and f"page {n} of 3" in intro["text"]
    header = fields(ex)
    assert header["header.account_name"].value == "TESTA SAMPLE MOCKERSON"
    assert header["header.period_from"].source_page == 1
    assert ex.cost_usd == 3 * Decimal("0.0188") + Decimal("0.042") + Decimal("0.041") + Decimal("0.042")


def test_balanced_bank_statement_gets_metrics_computed_in_python(ai, staff, users):
    p, doc = client_with(staff, "bank_statement", BANK)
    ex = read(users, p, doc, ai, response("bank_statement_page1"), response("bank_statement_page2"),
              response("bank_statement_page3"))
    assert ex.status == "completed", ex.status_reason
    assert all(pg.status == "balanced" for pg in pages(ex).values())
    assert metric_values(ex) == {
        "statement_months_covered": Decimal("3.0000"),
        "avg_monthly_inflow": Decimal("81666.6700"),
        "inflow_regularity": Decimal("1.0000"),
        "returned_items_count": Decimal("1.0000"),
        "returned_items_total": Decimal("5000.0000"),
        "lender_repayments_count": Decimal("3.0000"),
        "lender_repayments_total": Decimal("9500.0000"),
        "lender_repayments_monthly_avg": Decimal("3166.6700"),
    }
    assert inputs(ex, "returned_items_count") == ["CHQ 000123 RTD INSUFF FUNDS"]
    assert inputs(ex, "lender_repayments_total") == ["FULIZA M-PESA REPAYMENT", "FULIZA REPAYMENT",
                                                     "TALA LOAN REPAYMENT"]
    assert len(inputs(ex, "avg_monthly_inflow")) == 4  # three salaries and the cheque deposit
    m = StatementMetric.query.filter_by(extraction_id=ex.id, metric="avg_monthly_inflow").one()
    assert (m.period_from, m.period_to, m.unit) == (date(2026, 7, 1), date(2026, 9, 30), "KES")
    assert m.to_dict()["value"] == "81666.67"


def test_mpesa_statement_newest_first_is_checked_and_measured(ai, staff, users):
    p, doc = client_with(staff, "mpesa_statement", MPESA)
    ex = read(users, p, doc, ai, response("mpesa_statement_page1"), response("mpesa_statement_page2"))
    assert ex.status == "completed", ex.status_reason
    got = pages(ex)
    assert (got[1].opening_balance, got[1].closing_balance) == (Decimal("13800.00"), Decimal("25800.00"))
    assert (got[2].opening_balance, got[2].closing_balance) == (Decimal("3000.00"), Decimal("13800.00"))
    rows = txns(ex)
    assert (rows[0].page_number, rows[0].row_no, rows[0].txn_date, rows[0].reference) == \
        (1, 1, date(2026, 9, 3), "UAS0000005")  # stored oldest first
    values = metric_values(ex)
    assert (values["statement_months_covered"], values["avg_monthly_inflow"], values["inflow_regularity"]) == \
        (Decimal("2"), Decimal("17750.00"), Decimal("1.0000"))
    assert (values["lender_repayments_count"], values["lender_repayments_total"],
            values["lender_repayments_monthly_avg"]) == (Decimal("2"), Decimal("4700.00"), Decimal("2350.00"))
    assert values["returned_items_count"] == 0
    assert inputs(ex, "lender_repayments_count") == ["Fuliza M-Pesa Repayment", "M-Shwari Loan Repayment"]


def test_a_statement_of_the_wrong_type_stops_after_the_first_page(ai, staff, users):
    answer = recorded("bank_statement_page1")["answer"]
    answer["detected_document_type"] = "mpesa_statement"
    p, doc = client_with(staff, "bank_statement", BANK)
    ex = read(users, p, doc, ai, response("bank_statement_page1", answer=answer))
    assert ex.status == "rescan_needed" and "looks like an M-Pesa statement, not a Bank statement" in ex.status_reason
    assert len(ai.calls) == 1 and txns(ex) == [] and pages(ex) == {}


def test_an_unreadable_page_needs_a_rescan_of_that_page(ai, staff, users):
    blurred = recorded("bank_statement_page2")["answer"]
    blurred.update(readable=False, unreadable_reason="The page is a dark, skewed photo", transactions=[])
    p, doc = client_with(staff, "bank_statement", BANK)
    ex = read(users, p, doc, ai, response("bank_statement_page1"), response("bank_statement_page2", answer=blurred),
              response("bank_statement_page3"))
    assert ex.status == "rescan_needed" and ex.readable is False
    assert ex.status_reason.startswith("Page(s) 2 need a better copy.") and "dark, skewed photo" in ex.status_reason
    got = pages(ex)
    assert got[2].status == "rescan_needed" and got[3].status == "balanced"  # p3 can't continue from p2: own opening
    assert metric_values(ex) == {}


def test_a_failed_call_on_any_page_fails_the_whole_statement(ai, staff, users):
    p, doc = client_with(staff, "bank_statement", BANK)
    ex = read(users, p, doc, ai, response("bank_statement_page1"), response("bank_statement_page2"),
              api_error(400, "bad page"))
    assert ex.status == "failed" and pages(ex) == {} and txns(ex) == []
    assert [c.outcome for c in calls(ex)] == ["ok", "ok", "permanent_error"]  # the spend is still on record
    assert ex.cost_usd > 0


# ── The checks themselves ──


def _row(n, debit=None, credit=None, balance=None, day=1, month=7, desc=""):
    return Row(n, date(2026, month, day), desc, None, debit and Decimal(debit), credit and Decimal(credit),
               balance and Decimal(balance), None)


def test_page_check_to_the_cent_and_page_continuity():
    rows = [_row(1, credit="100.00", balance="1100.00"), _row(2, debit="0.01", balance="1099.99")]
    ok = check_page(rows, Decimal("1000.00"), Decimal("1099.99"), None)
    assert ok.status == "balanced" and ok.difference == 0
    off = check_page(rows, Decimal("1000.00"), Decimal("1100.00"), None)
    assert off.status == "needs_review" and off.difference == Decimal("-0.01")
    gap = check_page(rows, Decimal("1000.00"), Decimal("1099.99"), Decimal("900.00"))
    assert gap.status == "needs_review" and "a page may be missing" in " ".join(gap.problems)
    derived = check_page(rows, None, None, None)  # opening worked back from row 1, closing from the last row
    assert (derived.opening, derived.closing, derived.status) == (Decimal("1000.00"), Decimal("1099.99"), "balanced")
    nothing = check_page([_row(1, debit="5.00")], None, None, None)
    assert nothing.status == "needs_review" and "can be worked out" in " ".join(nothing.problems)


def test_metrics_by_hand_including_a_month_without_inflows():
    rows = [SimpleNamespace(txn_date=date(2026, 1, 5), description="SALARY", debit=None, credit=Decimal("100.00")),
            SimpleNamespace(txn_date=date(2026, 3, 5), description="SALARY", debit=None, credit=Decimal("50.00")),
            SimpleNamespace(txn_date=date(2026, 3, 9), description="STRTDX SHOP", debit=Decimal("10.00"), credit=None),
            SimpleNamespace(txn_date=date(2026, 3, 9), description="Chq 9 rtd", debit=Decimal("20.00"), credit=None),
            SimpleNamespace(txn_date=date(2026, 2, 2), description="tala repayment", debit=Decimal("7.00"),
                            credit=None)]
    got, start, end = metrics.compute(rows, None, None, ["TALA"], ["RTD"])
    values = {m.key: m.value for m in got}
    assert (start, end) == (date(2026, 1, 5), date(2026, 3, 9))
    assert values["statement_months_covered"] == 3
    assert values["avg_monthly_inflow"] == Decimal("50.00")
    assert values["inflow_regularity"] == Decimal("0.6667")  # January and March, not February
    assert (values["returned_items_count"], values["returned_items_total"]) == (1, Decimal("20.00"))  # not STRTDX
    assert (values["lender_repayments_total"], values["lender_repayments_monthly_avg"]) == \
        (Decimal("7.00"), Decimal("2.33"))
    assert metrics.months_between(date(2025, 11, 30), date(2026, 2, 1)) == [(2025, 11), (2025, 12), (2026, 1),
                                                                         (2026, 2)]
    assert metrics.compute([], None, None, ["TALA"], ["RTD"])[0] == []


@pytest.mark.parametrize("bad, problem", [({"debit": "1,2x"}, "isn't an amount"), ({"date": "31/02/2026"},
                                                                                       "isn't a date"),
                                          ({"debit": None, "credit": None}, "no amount was read")])
def test_rows_that_cannot_be_read_as_data_flag_the_page(ai, staff, users, bad, problem):
    answer = recorded("bank_statement_page3")["answer"]
    answer["transactions"][1].update(bad)
    p, doc = client_with(staff, "bank_statement", BANK)
    ex = read(users, p, doc, ai, response("bank_statement_page1"), response("bank_statement_page2"),
              response("bank_statement_page3", answer=answer))
    assert ex.status == "needs_review" and problem in pages(ex)[3].reason


# ── Lender keywords (version 2: Kenyan lenders, to be extended by credit) ──


def test_ai_05_kenyan_lender_keyword_list_is_seeded_as_a_new_version():
    from app.Settings.model import SettingVersion
    from app.Settings.registry import KENYAN_LENDER_KEYWORDS, REGISTRY, keyword_list

    v2 = SettingVersion.query.filter_by(key="ai.statements.lender_keywords", version_no=2).one()
    assert v2.value == keyword_list()(list(KENYAN_LENDER_KEYWORDS))
    assert {"FULIZA", "M-SHWARI LOAN", "KCB M-PESA LOAN", "HUSTLER FUND", "TALA", "BRANCH INTERNATIONAL",
            "ZENKA", "LOAN REPAYMENT"} <= set(v2.value)
    assert "M-SHWARI" not in v2.value and "BRANCH" not in v2.value  # would catch savings and bank branches
    assert "TO BE EXTENDED BY CREDIT" in v2.evidence
    assert "TO BE EXTENDED BY CREDIT" in REGISTRY["ai.statements.lender_keywords"].description


@pytest.mark.parametrize("description, expected", [
    ("Fuliza M-Pesa Repayment", "FULIZA"),
    ("fuliza m-pesa repayment", "FULIZA"),                       # any case
    ("M-Shwari Loan Repayment", "M-SHWARI LOAN"),
    ("M-Shwari Deposit", None),                                  # savings, not a loan
    ("kcb m-pesa loan repayment", "KCB M-PESA LOAN"),             # earliest, then longest, phrase is recorded
    ("Pay Bill to 849000 Tala", "TALA"),
    ("BRANCH WITHDRAWAL KAREN", None),                           # a bank branch, not Branch the lender
    ("HUSTLER FUND REPAYMENT", "HUSTLER FUND"),
    ("CAPITAL GAINS", None),
])
def test_ai_05_lender_keywords_match_whole_words_in_any_case(description, expected):
    from app.Settings.registry import KENYAN_LENDER_KEYWORDS
    assert metrics.matched_keyword(description, KENYAN_LENDER_KEYWORDS) == expected


def test_ai_05_the_matched_keyword_is_recorded_and_logged(ai, staff, users, admin1, caplog, monkeypatch):
    import logging
    # Alembic's fileConfig (run when the test DB is migrated) disables loggers that already exist.
    monkeypatch.setattr(logging.getLogger("app.DocAI.metrics"), "disabled", False)
    caplog.set_level(logging.INFO, logger="app.DocAI.metrics")
    p, doc = client_with(staff, "bank_statement", BANK)
    ex = read(users, p, doc, ai, response("bank_statement_page1"), response("bank_statement_page2"),
              response("bank_statement_page3"))
    body = admin1.get(f"/api/v1/extractions/{ex.id}").get_json()["data"]
    lenders = next(m for m in body["metrics"] if m["metric"] == "lender_repayments_total")
    by_description = {next(t["description"] for t in body["transactions"] if str(t["id"]) == tid): word
                      for tid, word in lenders["matched_keywords"].items()}
    assert by_description == {"FULIZA REPAYMENT": "FULIZA", "TALA LOAN REPAYMENT": "TALA",
                              "FULIZA M-PESA REPAYMENT": "FULIZA"}
    returned = next(m for m in body["metrics"] if m["metric"] == "returned_items_count")
    assert list(returned["matched_keywords"].values()) == ["RTD"]  # "CHQ 000123 RTD INSUFF FUNDS": the first match
    assert "lender keyword 'FULIZA' matched transaction" in caplog.text
    assert "SAMPLE" not in caplog.text  # only the keyword and transaction id are logged, not the narration
