"""
Balance arithmetic — the single place that defines what an investor's balance is.

    balance(as of D) = Σ posted deposits (value_date ≤ D) − Σ approved withdrawals (value_date ≤ D)

Value dates are never in the future (enforced when recording), so "as of today"
is simply the sum over everything posted/approved.

    available = balance − Σ active (unreleased) account_holds on the investor's account

A pending withdrawal is a hold (reason 'pending_withdrawal'): placed when it is
requested, released when it is approved or rejected.
"""
from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import func

from app.database.database import db
from app.Interest.model import LOCKED_PERIOD_STATUSES, InterestPeriod
from app.Investors.model import Investor
from app.Parties.model import HOLD_PENDING_WITHDRAWAL, AccountHold
from app.Transactions.model import (
    DEPOSIT_POSTED,
    WITHDRAWAL_APPROVED,
    Deposit,
    Withdrawal,
)
from app.utils.dates import utcnow
from app.utils.http import NotFound, ValidationError
from app.utils.money import ZERO


def lock_investor(investor_id: int) -> Investor:
    """SELECT ... FOR UPDATE on the investor row. Every write that changes or
    depends on a balance takes this lock first, so two concurrent approvals
    can't each see enough balance and together overdraw the account."""
    investor = db.session.query(Investor).filter(Investor.id == investor_id).with_for_update().first()
    if investor is None:
        raise NotFound("Investor not found.")
    return investor


def locked_through() -> date | None:
    """Last day covered by an approved/paid interest period. Nothing may be
    backdated to or before this date — those statements have gone out."""
    return (
        db.session.query(func.max(InterestPeriod.period_end))
        .filter(InterestPeriod.status.in_(LOCKED_PERIOD_STATUSES))
        .scalar()
    )


def assert_not_locked(value_date: date, what: str) -> None:
    locked = locked_through()
    if locked is not None and value_date <= locked:
        raise ValidationError(
            f"{what} dated {value_date.isoformat()} falls in an interest period that has already been "
            f"approved (locked through {locked.isoformat()}). Use a later date."
        )


def _deposits_total(investor_id: int, through: date | None = None) -> Decimal:
    q = db.session.query(func.coalesce(func.sum(Deposit.amount), 0)).filter(
        Deposit.investor_id == investor_id, Deposit.status == DEPOSIT_POSTED
    )
    if through is not None:
        q = q.filter(Deposit.value_date <= through)
    return Decimal(q.scalar())


def _withdrawals_total(investor_id: int, through: date | None = None) -> Decimal:
    q = db.session.query(func.coalesce(func.sum(Withdrawal.amount), 0)).filter(
        Withdrawal.investor_id == investor_id, Withdrawal.status == WITHDRAWAL_APPROVED
    )
    if through is not None:
        q = q.filter(Withdrawal.value_date <= through)
    return Decimal(q.scalar())


def balance_as_of(investor_id: int, as_of: date | None = None) -> Decimal:
    return _deposits_total(investor_id, as_of) - _withdrawals_total(investor_id, as_of)


def _holds_query(investor_id: int, reason: str | None):
    q = (
        db.session.query(func.coalesce(func.sum(AccountHold.amount), 0))
        .join(Investor, Investor.account_id == AccountHold.account_id)
        .filter(Investor.id == investor_id, AccountHold.released_at.is_(None))
    )
    if reason is not None:
        q = q.filter(AccountHold.reason == reason)
    return q


def holds_total(investor_id: int) -> Decimal:
    """Everything held on the investor's account now, whatever the reason."""
    return Decimal(_holds_query(investor_id, None).scalar())


def pending_withdrawals_total(investor_id: int) -> Decimal:
    return Decimal(_holds_query(investor_id, HOLD_PENDING_WITHDRAWAL).scalar())


def available_balance(investor_id: int) -> Decimal:
    return balance_as_of(investor_id) - holds_total(investor_id)


def place_hold(investor: Investor, amount: Decimal, reason: str, reference_type: str, reference_id: int,
               actor: str) -> AccountHold:
    """Adds the hold without committing. The caller holds lock_investor() and commits it with the
    business change."""
    hold = AccountHold(account_id=investor.account_id, amount=amount, reason=reason,
                       reference_type=reference_type, reference_id=reference_id,
                       placed_by=actor, placed_at=utcnow())
    db.session.add(hold)
    db.session.flush()
    return hold


def release_hold(reason: str, reference_type: str, reference_id: int, actor: str) -> AccountHold:
    """Releases the active hold for a reference without committing (caller holds lock_investor())."""
    hold = AccountHold.query.filter_by(reason=reason, reference_type=reference_type, reference_id=reference_id,
                                       released_at=None).first()
    if hold is None:
        raise ValidationError(f"No active {reason.replace('_', ' ')} hold for {reference_type} {reference_id}.")
    hold.released_by = actor
    hold.released_at = utcnow()
    db.session.flush()
    return hold


def balance_events(investor_ids: list[int] | None, through: date) -> dict[int, list[tuple[date, Decimal]]]:
    """Every balance movement up to `through`, per investor, oldest first, as
    (value_date, signed amount). Used by the interest calculator."""
    events: dict[int, list[tuple[date, Decimal]]] = defaultdict(list)

    dq = db.session.query(Deposit.investor_id, Deposit.value_date, Deposit.amount).filter(
        Deposit.status == DEPOSIT_POSTED, Deposit.value_date <= through
    )
    wq = db.session.query(Withdrawal.investor_id, Withdrawal.value_date, Withdrawal.amount).filter(
        Withdrawal.status == WITHDRAWAL_APPROVED, Withdrawal.value_date <= through
    )
    if investor_ids is not None:
        dq = dq.filter(Deposit.investor_id.in_(investor_ids))
        wq = wq.filter(Withdrawal.investor_id.in_(investor_ids))

    for inv_id, d, amount in dq:
        events[inv_id].append((d, Decimal(amount)))
    for inv_id, d, amount in wq:
        events[inv_id].append((d, -Decimal(amount)))

    for inv_events in events.values():
        inv_events.sort(key=lambda e: e[0])
    return events


def min_balance_from(investor_id: int, start: date) -> Decimal:
    """Lowest end-of-day balance on any date from `start` onwards (to today).

    Removing X from the balance as of `start` — approving a withdrawal or
    reversing a deposit with that value date — is only safe if this minus X
    stays ≥ 0; otherwise some later day would go negative."""
    balance = balance_as_of(investor_id, start)
    lowest = balance
    later = defaultdict(Decimal)
    for d, delta in balance_events([investor_id], date.max).get(investor_id, []):
        if d > start:
            later[d] += delta
    for d in sorted(later):
        balance += later[d]
        lowest = min(lowest, balance)
    return lowest


def investor_totals(investor_id: int) -> dict:
    from app.Interest.model import PAYOUT_PAID, PAYOUT_PENDING, InterestPayout

    deposited = _deposits_total(investor_id)
    withdrawn = _withdrawals_total(investor_id)

    def _payout_sum(status: str) -> Decimal:
        total = (
            db.session.query(func.coalesce(func.sum(InterestPayout.net_interest), 0))
            .join(InterestPeriod, InterestPeriod.id == InterestPayout.period_id)
            .filter(
                InterestPayout.investor_id == investor_id,
                InterestPayout.status == status,
                InterestPeriod.status.in_(LOCKED_PERIOD_STATUSES),
            )
            .scalar()
        )
        return Decimal(total)

    return {
        "balance": deposited - withdrawn,
        "total_deposited": deposited,
        "total_withdrawn": withdrawn,
        "pending_withdrawals": pending_withdrawals_total(investor_id),
        "interest_paid": _payout_sum(PAYOUT_PAID),
        "interest_payable": _payout_sum(PAYOUT_PENDING),
    }


def balances_subquery():
    """(investor_id, balance, pending_withdrawals) for every investor — for
    directory listings and dashboard totals in a single query."""
    dep = (
        db.session.query(Deposit.investor_id.label("investor_id"), func.sum(Deposit.amount).label("total"))
        .filter(Deposit.status == DEPOSIT_POSTED)
        .group_by(Deposit.investor_id)
        .subquery()
    )
    wd = (
        db.session.query(Withdrawal.investor_id.label("investor_id"), func.sum(Withdrawal.amount).label("total"))
        .filter(Withdrawal.status == WITHDRAWAL_APPROVED)
        .group_by(Withdrawal.investor_id)
        .subquery()
    )
    pend = (
        db.session.query(AccountHold.account_id.label("account_id"), func.sum(AccountHold.amount).label("total"))
        .filter(AccountHold.reason == HOLD_PENDING_WITHDRAWAL, AccountHold.released_at.is_(None))
        .group_by(AccountHold.account_id)
        .subquery()
    )
    return (
        db.session.query(
            Investor.id.label("investor_id"),
            (func.coalesce(dep.c.total, 0) - func.coalesce(wd.c.total, 0)).label("balance"),
            func.coalesce(pend.c.total, 0).label("pending_withdrawals"),
        )
        .outerjoin(dep, dep.c.investor_id == Investor.id)
        .outerjoin(wd, wd.c.investor_id == Investor.id)
        .outerjoin(pend, pend.c.account_id == Investor.account_id)
        .subquery()
    )


def ledger_entries(investor_id: int, start: date | None = None, end: date | None = None) -> dict:
    """Chronological statement lines with a running balance, between start and
    end inclusive (all time if omitted). Reversed deposits and non-approved
    withdrawals don't move the balance, so they aren't listed."""
    opening = balance_as_of(investor_id, start.fromordinal(start.toordinal() - 1)) if start else ZERO

    rows = []
    dq = Deposit.query.filter(Deposit.investor_id == investor_id, Deposit.status == DEPOSIT_POSTED)
    wq = Withdrawal.query.filter(Withdrawal.investor_id == investor_id, Withdrawal.status == WITHDRAWAL_APPROVED)
    if start:
        dq = dq.filter(Deposit.value_date >= start)
        wq = wq.filter(Withdrawal.value_date >= start)
    if end:
        dq = dq.filter(Deposit.value_date <= end)
        wq = wq.filter(Withdrawal.value_date <= end)

    for dep in dq:
        rows.append({"kind": "deposit", "id": dep.id, "date": dep.value_date, "reference": dep.reference,
                     "method": dep.method, "amount": Decimal(dep.amount), "sort": (dep.value_date, 0, dep.id)})
    for wd in wq:
        rows.append({"kind": "withdrawal", "id": wd.id, "date": wd.value_date,
                     "reference": wd.payment_reference or "", "method": wd.method,
                     "amount": -Decimal(wd.amount), "sort": (wd.value_date, 1, wd.id)})
    rows.sort(key=lambda r: r["sort"])

    running = opening
    for r in rows:
        running += r["amount"]
        r["balance"] = running
        del r["sort"]

    return {"opening_balance": opening, "closing_balance": running, "entries": rows}
