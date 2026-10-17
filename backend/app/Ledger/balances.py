"""
GL balances. The only module that adds up journal lines (03 ADR-03-4); a test
fails if another module sums them.

Balances are by value date and signed on the account's normal side: a debit
account's balance is debits − credits, a credit account's credits − debits.
A header account's balance includes all its sub-accounts, signed on the
header's side (so contra accounts reduce it).
"""
from datetime import date
from decimal import Decimal

from sqlalchemy import func

from app.database.database import db
from app.Ledger.accounts import descendant_ids, get_account
from app.Ledger.model import GlAccount, JournalEntry, JournalLine
from app.utils.money import as_str

ZERO = Decimal("0.00")


def _signed(account: GlAccount, debit: Decimal, credit: Decimal) -> Decimal:
    return (debit - credit) if account.normal_side == "debit" else (credit - debit)


def _scope(account: GlAccount, include_children: bool) -> list[int]:
    return [account.id, *(descendant_ids(account) if include_children else ())]


def _totals(account_ids, *, on_or_before: date | None = None, before: date | None = None,
            branch_id: int | None = None, account_id: int | None = None) -> tuple[Decimal, Decimal]:
    q = (db.session.query(func.coalesce(func.sum(JournalLine.debit), 0), func.coalesce(func.sum(JournalLine.credit), 0))
         .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
         .filter(JournalLine.gl_account_id.in_(account_ids)))
    if on_or_before is not None:
        q = q.filter(JournalEntry.value_date <= on_or_before)
    if before is not None:
        q = q.filter(JournalEntry.value_date < before)
    if branch_id is not None:
        q = q.filter(JournalLine.branch_id == branch_id)
    if account_id is not None:
        q = q.filter(JournalLine.account_id == account_id)
    debit, credit = q.one()
    return Decimal(debit), Decimal(credit)


def account_balance(gl_account_id: int, as_of: date, branch_id: int | None = None,
                    include_children: bool = True) -> Decimal:
    account = get_account(gl_account_id)
    debit, credit = _totals(_scope(account, include_children), on_or_before=as_of, branch_id=branch_id)
    return _signed(account, debit, credit)


def subledger_balance(gl_account_id: int, account_id: int, as_of: date) -> Decimal:
    """One client account's balance on a control account (e.g. an investor on 2100)."""
    account = get_account(gl_account_id)
    debit, credit = _totals([account.id], on_or_before=as_of, account_id=account_id)
    return _signed(account, debit, credit)


def trial_balance(as_of: date, branch_id: int | None = None) -> dict:
    """Every account with postings up to as_of, its balance in the debit or credit column, and the totals."""
    q = (db.session.query(JournalLine.gl_account_id, func.sum(JournalLine.debit), func.sum(JournalLine.credit))
         .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
         .filter(JournalEntry.value_date <= as_of))
    if branch_id is not None:
        q = q.filter(JournalLine.branch_id == branch_id)
    sums = {gl_id: (Decimal(d), Decimal(c)) for gl_id, d, c in q.group_by(JournalLine.gl_account_id)}
    accounts = GlAccount.query.filter(GlAccount.id.in_(sums)).order_by(GlAccount.code).all() if sums else []
    rows, total_debit, total_credit = [], ZERO, ZERO
    for account in accounts:
        debit, credit = sums[account.id]
        net = debit - credit
        row_debit, row_credit = (net, ZERO) if net > 0 else (ZERO, -net)
        total_debit, total_credit = total_debit + row_debit, total_credit + row_credit
        rows.append({"gl_account_id": account.id, "code": account.code, "name": account.name,
                     "account_type": account.account_type, "normal_side": account.normal_side,
                     "debit_total": as_str(debit), "credit_total": as_str(credit),
                     "debit": as_str(row_debit), "credit": as_str(row_credit),
                     "balance": as_str(_signed(account, debit, credit))})
    return {"as_of": as_of.isoformat(), "branch_id": branch_id, "rows": rows,
            "total_debit": as_str(total_debit), "total_credit": as_str(total_credit),
            "balanced": total_debit == total_credit}


def account_statement(gl_account_id: int, date_from: date, date_to: date, branch_id: int | None = None,
                      include_children: bool = True) -> dict:
    """Opening balance, every line in the range by value date and journal number, the running balance, closing."""
    account = get_account(gl_account_id)
    scope = _scope(account, include_children)
    opening = _signed(account, *_totals(scope, before=date_from, branch_id=branch_id))
    q = (db.session.query(JournalLine, JournalEntry, GlAccount.code)
         .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
         .join(GlAccount, GlAccount.id == JournalLine.gl_account_id)
         .filter(JournalLine.gl_account_id.in_(scope), JournalEntry.value_date >= date_from,
                 JournalEntry.value_date <= date_to))
    if branch_id is not None:
        q = q.filter(JournalLine.branch_id == branch_id)
    q = q.order_by(JournalEntry.value_date, JournalEntry.financial_year, JournalEntry.seq_no, JournalLine.line_no)
    running, lines, debits, credits = opening, [], ZERO, ZERO
    for line, entry, code in q:
        running += _signed(account, line.debit, line.credit)
        debits, credits = debits + line.debit, credits + line.credit
        lines.append({"value_date": entry.value_date.isoformat(), "journal_no": entry.journal_no,
                      "entry_id": entry.id, "gl_code": code, "description": line.description or entry.description,
                      "branch_id": line.branch_id, "account_id": line.account_id,
                      "debit": as_str(line.debit), "credit": as_str(line.credit), "balance": as_str(running)})
    return {"account": account.to_dict(), "from": date_from.isoformat(), "to": date_to.isoformat(),
            "branch_id": branch_id, "opening_balance": as_str(opening), "lines": lines,
            "total_debit": as_str(debits), "total_credit": as_str(credits), "closing_balance": as_str(running)}

