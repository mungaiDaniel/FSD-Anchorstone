"""
Bank and M-Pesa statements (05 §6; FSD §15 "Long statements").

The model is called once per page and only lists the rows and the balances printed
on that page. Python then checks every page, to the cent:

    opening + Σ credits − Σ debits = closing

  opening  the balance printed as brought forward / opening; else, when the rows run
           oldest first, the previous page's closing; else worked back from the first
           row's running balance
  closing  the balance printed as carried forward / closing; else the last row's balance

and that each row's running balance follows from the one before. A difference marks
the page 'needs_review' with the figures, the main protection against a misread
amount. A page whose opening differs from the previous page's printed closing is
flagged too (a missing page).

Only when every page balances are the metrics computed (metrics.py), from the
stored transactions, each linked to the rows it used.
"""
from dataclasses import dataclass, field
from decimal import Decimal

from app.database.database import db
from app.DocAI import metrics, validators
from app.DocAI.model import (
    EXTRACTION_COMPLETED,
    EXTRACTION_NEEDS_REVIEW,
    EXTRACTION_RESCAN,
    PAGE_BALANCED,
    PAGE_NEEDS_REVIEW,
    PAGE_RESCAN,
    StatementPage,
    StatementTransaction,
)
from app.utils.money import fmt_kes

ZERO = Decimal("0.00")


@dataclass
class Row:
    row_no: int
    date: object
    description: str | None
    reference: str | None
    debit: Decimal | None
    credit: Decimal | None
    balance: Decimal | None
    confidence: Decimal | None


@dataclass
class PageCheck:
    status: str
    opening: Decimal | None = None
    closing: Decimal | None = None
    credits: Decimal = ZERO
    debits: Decimal = ZERO
    computed: Decimal | None = None
    difference: Decimal | None = None
    problems: list[str] = field(default_factory=list)


def parse_rows(answer: dict) -> tuple[list[Row], list[str]]:
    """The page's rows, oldest first and numbered from 1, and any value that isn't readable as data."""
    problems = []
    raw = list(answer.get("transactions") or [])
    if answer.get("rows_order") == "newest_first":
        raw.reverse()
    rows = []
    for i, r in enumerate(raw, 1):
        label = f"Row {r.get('row', i)}"
        date = validators.parse_iso_date(r.get("date"))
        if r.get("date") and date is None:
            problems.append(f"{label}: '{r['date']}' isn't a date.")
        amounts = {}
        for side in ("debit", "credit", "balance"):
            text = r.get(side)
            amounts[side] = validators.parse_money(text, signed=side == "balance") if text not in (None, "") else None
            if text not in (None, "") and amounts[side] is None:
                problems.append(f"{label}: {side} '{text}' isn't an amount.")
        if amounts["debit"] is None and amounts["credit"] is None and not any(
                p.startswith(label + ":") for p in problems):
            problems.append(f"{label}: no amount was read.")
        confidence = r.get("confidence")
        rows.append(Row(i, date, r.get("description"), r.get("reference"), amounts["debit"], amounts["credit"],
                        amounts["balance"],
                        None if confidence is None else Decimal(str(confidence)).quantize(Decimal("0.001"))))
    return rows, problems


def _printed(answer: dict, key: str, problems: list[str]) -> Decimal | None:
    value = (answer.get(key) or {}).get("value")
    if value in (None, ""):
        return None
    amount = validators.parse_money(value, signed=True)
    if amount is None:
        problems.append(f"The {key.replace('page_', '').replace('_', ' ')} '{value}' isn't an amount.")
    return amount


def check_page(rows: list[Row], printed_opening: Decimal | None, printed_closing: Decimal | None,
               previous_closing: Decimal | None, problems: list[str] | None = None) -> PageCheck:
    out = PageCheck(PAGE_BALANCED, problems=list(problems or []))
    out.credits = sum((r.credit or ZERO for r in rows), ZERO)
    out.debits = sum((r.debit or ZERO for r in rows), ZERO)
    opening = printed_opening
    if opening is None and previous_closing is not None:
        opening = previous_closing
    if opening is None and rows and rows[0].balance is not None:
        opening = rows[0].balance - (rows[0].credit or ZERO) + (rows[0].debit or ZERO)
    if printed_opening is not None and previous_closing is not None and printed_opening != previous_closing:
        out.problems.append(f"The opening balance {fmt_kes(printed_opening)} doesn't match the previous page's "
                            f"closing balance {fmt_kes(previous_closing)}: a page may be missing or misread.")
    closing = printed_closing
    if closing is None and rows and rows[-1].balance is not None:
        closing = rows[-1].balance
    out.opening, out.closing = opening, closing
    if opening is None or closing is None:
        out.problems.append("No opening or closing balance is printed on this page, and none can be worked out "
                            "from running balances.")
    else:
        out.computed = opening + out.credits - out.debits
        out.difference = out.computed - closing
        if out.difference != ZERO:
            out.problems.append(
                f"Opening {fmt_kes(opening)} + credits {fmt_kes(out.credits)} − debits {fmt_kes(out.debits)} = "
                f"{fmt_kes(out.computed)}, but the page shows {fmt_kes(closing)} "
                f"(difference {fmt_kes(out.difference)}).")
        running, broken = opening, []
        for r in rows:
            running = running + (r.credit or ZERO) - (r.debit or ZERO)
            if r.balance is not None:
                if r.balance != running:
                    broken.append(str(r.row_no))
                running = r.balance  # carry on from what is printed, so one misread flags one row
        if broken:
            out.problems.append(f"The running balance doesn't follow on row(s) {', '.join(broken)} (oldest first).")
    if out.problems:
        out.status = PAGE_NEEDS_REVIEW
    return out


def read(ex, t, prepared, client, system: str, schema: dict, api_schema: dict) -> None:
    """Ask for each page, then check and store. A failed call (CallFailed) stops the whole document."""
    from app.DocAI.extractor import ask, check_identity, finish, intro, store_field

    answers = []
    for n, block in enumerate(prepared.pages, 1):
        answer = ask(ex, client, system, [block, {"type": "text", "text": intro(t, prepared.page_count, n)}],
                     schema, api_schema, page=n)
        answers.append((n, answer))
        if n == 1 and answer["readable"] and answer["detected_document_type"] != ex.declared_type:
            break  # the wrong document: don't pay to read the rest
    first = next((a for _, a in answers if a["readable"]), answers[0][1])
    ex.detected_document_type = first["detected_document_type"]
    ex.readable = all(a["readable"] for _, a in answers)
    ex.warnings = [f"Page {n}: {w}" for n, a in answers for w in (a.get("warnings") or [])] or None
    page_one = answers[0][1]
    if page_one["readable"] and page_one["detected_document_type"] != ex.declared_type:
        return finish(ex, EXTRACTION_RESCAN, check_identity(ex, page_one["detected_document_type"], True, None))

    header_done = False
    previous_closing = None
    all_rows: list[StatementTransaction] = []
    rescan, review = [], []
    for n, answer in answers:
        rescan_reason = check_identity(ex, answer["detected_document_type"], answer["readable"],
                                       answer.get("unreadable_reason"), where=f" on page {n}")
        if rescan_reason:
            db.session.add(StatementPage(extraction_id=ex.id, page_number=n, status=PAGE_RESCAN,
                                         reason=rescan_reason, transaction_count=0))
            rescan.append((n, rescan_reason))
            previous_closing = None
            continue
        header = answer.get("header") or {}
        if not header_done and any((header.get(f.name) or {}).get("value") for f in t.fields):
            for f in t.fields:
                store_field(ex, f"header.{f.name}", f.kind, header.get(f.name), ex.page_count, page_override=n)
            header_done = True
        rows, problems = parse_rows(answer)
        printed_opening = _printed(answer, "page_opening_balance", problems)
        printed_closing = _printed(answer, "page_closing_balance", problems)
        oldest_first = answer.get("rows_order") != "newest_first"
        result = check_page(rows, printed_opening, printed_closing, previous_closing if oldest_first else None,
                            problems)
        previous_closing = result.closing if oldest_first else None
        for r in rows:
            txn = StatementTransaction(extraction_id=ex.id, page_number=n, row_no=r.row_no, txn_date=r.date,
                                       description=r.description, reference=(r.reference or None) and
                                       str(r.reference)[:120], debit=r.debit, credit=r.credit, balance=r.balance,
                                       confidence=r.confidence)
            db.session.add(txn)
            all_rows.append(txn)
        db.session.add(StatementPage(
            extraction_id=ex.id, page_number=n, status=result.status, opening_balance=result.opening,
            closing_balance=result.closing, credits_total=result.credits, debits_total=result.debits,
            computed_closing=result.computed, difference=result.difference, transaction_count=len(rows),
            reason=" ".join(result.problems) or None))
        if result.status != PAGE_BALANCED:
            review.append((n, " ".join(result.problems)))
    db.session.flush()

    if rescan:
        pages = ", ".join(str(n) for n, _ in rescan)
        return finish(ex, EXTRACTION_RESCAN, f"Page(s) {pages} need a better copy. {rescan[0][1]}")
    if review:
        pages = ", ".join(str(n) for n, _ in review)
        detail = " ".join(f"Page {n}: {why}" for n, why in review)
        return finish(ex, EXTRACTION_NEEDS_REVIEW, f"Page(s) {pages} don't add up, so no figures were worked out "
                                                   f"until they are checked. {detail}"[:4000])
    metrics.store(ex, all_rows)
    finish(ex, EXTRACTION_COMPLETED)
