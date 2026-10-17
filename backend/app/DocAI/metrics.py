"""
Statement metrics, computed in Python from the stored transactions, never by the
model (05 ADR-05-1, §6.2; FSD §15 "Calculations by the system"). Only for a
statement whose every page balanced.

    statement_months_covered       calendar months from the period start to its end, both
                                   counted (the printed period; else the first and last
                                   transaction dates)
    avg_monthly_inflow             Σ credits ÷ months covered, to the cent
    inflow_regularity              months with at least one credit ÷ months covered (4 dp)
    returned_items_count / _total  rows whose description contains a word in
                                   ai.statements.returned_item_keywords (amount in or out)
    lender_repayments_count /      debits whose description contains a word in
      _total / _monthly_avg        ai.statements.lender_keywords; the average ÷ months covered

Keywords match whole words, ignoring case ("RTD" matches "CHQ 123 RTD", not "STRTDX").
Each metric row is linked to the transactions it used (ai_statement_metric_inputs), with the
keyword that matched each one, which is also logged (transaction id and keyword only).
"""
import logging
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.database.database import db
from app.DocAI.model import ExtractedField, StatementMetric, StatementMetricInput
from app.DocAI.validators import parse_iso_date
from app.Settings import business
from app.utils.money import round_money

logger = logging.getLogger(__name__)
ZERO = Decimal("0.00")
RATIO = Decimal("0.0001")


@dataclass
class Metric:
    key: str
    value: Decimal
    unit: str
    definition: str
    inputs: list = field(default_factory=list)
    keywords: list = field(default_factory=list)  # the keyword each input matched (keyword metrics only)


def months_between(start: date, end: date) -> list[tuple[int, int]]:
    if end < start:
        start, end = end, start
    out, (y, m) = [], (start.year, start.month)
    while (y, m) <= (end.year, end.month):
        out.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def matched_keyword(description: str | None, keywords) -> str | None:
    """The keyword found as whole words in the description, ignoring case, or None. When several match,
    the one that appears first in the narration (it usually names the lender: "TALA LOAN REPAYMENT" →
    TALA), then the longest ("KCB M-PESA LOAN" over "KCB LOAN")."""
    text = (description or "").upper()
    best = None
    for k in keywords:
        found = re.search(rf"(?<![A-Z0-9]){re.escape(k.upper())}(?![A-Z0-9])", text)
        if found and (best is None or (found.start(), -len(k)) < (best[0], -len(best[1]))):
            best = (found.start(), k)
    return best[1] if best else None


def matches(description: str | None, keywords) -> bool:
    return matched_keyword(description, keywords) is not None


def keyword_rows(rows, keywords, *, debits_only: bool = False, kind: str = "keyword") -> tuple[list, list[str]]:
    """The rows whose description contains a keyword, and the keyword each matched (logged)."""
    hits, words = [], []
    for r in rows:
        if debits_only and not (r.debit and r.debit > 0):
            continue
        word = matched_keyword(r.description, keywords)
        if word:
            hits.append(r)
            words.append(word)
            logger.info("%s keyword %r matched transaction %s", kind, word, getattr(r, "id", None))
    return hits, words


def compute(rows, period_from: date | None, period_to: date | None, lender_keywords, returned_keywords) -> \
        tuple[list[Metric], date | None, date | None]:
    """rows: objects with txn_date, description, debit, credit. Returns ([], …) when there is no period."""
    dates = [r.txn_date for r in rows if r.txn_date]
    start = period_from or (min(dates) if dates else None)
    end = period_to or (max(dates) if dates else None)
    if start is None or end is None:
        return [], start, end
    months = months_between(start, end)
    n = Decimal(len(months))
    credits = [r for r in rows if r.credit and r.credit > 0]
    total_in = sum((r.credit for r in credits), ZERO)
    with_inflow = {(r.txn_date.year, r.txn_date.month) for r in credits if r.txn_date} & set(months)
    returned, returned_words = keyword_rows(rows, returned_keywords, kind="returned-item")
    lenders, lender_words = keyword_rows(rows, lender_keywords, debits_only=True, kind="lender")
    lender_total = sum((r.debit for r in lenders), ZERO)
    kw_returned = ", ".join(returned_keywords)
    kw_lenders = ", ".join(lender_keywords)
    out = [
        Metric("statement_months_covered", n, "months",
               f"Calendar months from {start.isoformat()} to {end.isoformat()}, both counted."),
        Metric("avg_monthly_inflow", round_money(total_in / n), "KES",
               f"Total credits {total_in:,.2f} ÷ {len(months)} month(s).", credits),
        Metric("inflow_regularity", (Decimal(len(with_inflow)) / n).quantize(RATIO, rounding=ROUND_HALF_UP), "ratio",
               f"{len(with_inflow)} of {len(months)} month(s) had at least one credit.", credits),
        Metric("returned_items_count", Decimal(len(returned)), "count",
               f"Rows mentioning any of: {kw_returned}.", returned, returned_words),
        Metric("returned_items_total", sum(((r.debit or r.credit or ZERO) for r in returned), ZERO), "KES",
               f"Amount of the rows mentioning any of: {kw_returned}.", returned, returned_words),
        Metric("lender_repayments_count", Decimal(len(lenders)), "count",
               f"Debits mentioning any of: {kw_lenders}.", lenders, lender_words),
        Metric("lender_repayments_total", lender_total, "KES",
               f"Total of the debits mentioning any of: {kw_lenders}.", lenders, lender_words),
        Metric("lender_repayments_monthly_avg", round_money(lender_total / n), "KES",
               f"Lender repayments {lender_total:,.2f} ÷ {len(months)} month(s).", lenders, lender_words),
    ]
    return out, start, end


def _period(extraction_id: int, name: str) -> date | None:
    row = ExtractedField.query.filter_by(extraction_id=extraction_id, field_path=f"header.{name}").first()
    return parse_iso_date(row.value) if row is not None and row.validation == "passed" else None


def store(ex, rows) -> list[StatementMetric]:
    """Compute and store the metrics of a statement whose pages all balanced (rows already flushed)."""
    lender_kw = business.get("ai.statements.lender_keywords")
    returned_kw = business.get("ai.statements.returned_item_keywords")
    computed, start, end = compute(rows, _period(ex.id, "period_from"), _period(ex.id, "period_to"), lender_kw,
                                   returned_kw)
    stored = []
    for m in computed:
        row = StatementMetric(extraction_id=ex.id, metric=m.key, value=m.value, unit=m.unit, period_from=start,
                              period_to=end, definition=m.definition)
        db.session.add(row)
        db.session.flush()
        words = m.keywords or [None] * len(m.inputs)
        for txn, word in zip(m.inputs, words):
            db.session.add(StatementMetricInput(metric_id=row.id, transaction_id=txn.id, matched_keyword=word))
        stored.append(row)
    db.session.flush()
    return stored
