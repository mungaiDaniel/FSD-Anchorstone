"""
Monthly interest: calculate (draft) → approve → mark paid.

Calculation (per investor, per day of the month):

    daily interest = closing balance that day × annual rate% ÷ 100 ÷ 365

  - fixed 365-day count (also in leap years), per Anchorstone's policy
  - closing balance = balance after that day's deposits and approved withdrawals
  - the rate for each day is the rate in effect on that day, so a mid-month
    rate change is handled day by day
  - the month's interest is summed at full precision and rounded to the cent
    once (half-up), so there is no per-day rounding drift
  - simple interest: interest is paid out, never added to the balance, so it
    never earns interest itself

Controls:
  - only whole calendar months that have ended can be calculated
  - months go in order: the next month after the last approved one (any month
    for the very first run); one draft at a time
  - maker-checker: the admin who approves must differ from the one who calculated
  - approval re-runs the calculation and refuses if anything changed since the
    draft (e.g. a backdated deposit) — recalculate and review again
  - approval locks the month: nothing can be backdated into it afterwards
"""
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func

from app.Approvals.policy import assert_can_decide
from app.database.database import db
from app.Emails.composer import queue_interest_statement
from app.Interest.model import (
    LOCKED_PERIOD_STATUSES,
    PAYOUT_PAID,
    PAYOUT_PENDING,
    PERIOD_APPROVED,
    PERIOD_DRAFT,
    PERIOD_PAID,
    InterestPayout,
    InterestPeriod,
    InterestRate,
)
from app.Investors.model import Investor
from app.Transactions.ledger import balance_events, locked_through
from app.utils.audit_log import create_audit_log
from app.utils.dates import month_bounds, parse_date, today_eat, utcnow
from app.utils.http import Conflict, NotFound, ValidationError
from app.utils.money import ZERO, as_str, fmt_kes, parse_rate_percent, round_money

DAY_COUNT = Decimal(365)
HUNDRED = Decimal(100)
# Withholding tax is not applied yet (pending compliance confirmation).
DEFAULT_TAX_RATE_PERCENT = Decimal("0")


@dataclass
class PayoutCalc:
    investor_id: int
    days: int
    opening_balance: Decimal
    closing_balance: Decimal
    balance_days: Decimal  # Σ daily closing balances
    gross_unrounded: Decimal

    @property
    def gross(self) -> Decimal:
        return round_money(self.gross_unrounded)

    @property
    def average_daily_balance(self) -> Decimal:
        return round_money(self.balance_days / self.days)

    @property
    def effective_rate_percent(self) -> Decimal:
        if self.balance_days == 0:
            return Decimal("0")
        return (self.gross_unrounded * DAY_COUNT * HUNDRED / self.balance_days).quantize(Decimal("0.0001"))


# ── Rates ─────────────────────────────────────────────────────────────────


def list_rates() -> list[InterestRate]:
    return InterestRate.query.order_by(InterestRate.effective_from.desc()).all()


def current_rate() -> InterestRate | None:
    return (
        InterestRate.query.filter(InterestRate.effective_from <= today_eat())
        .order_by(InterestRate.effective_from.desc())
        .first()
    )


def set_rate(data: dict, actor: str) -> InterestRate:
    rate = parse_rate_percent(data.get("rate_percent"))
    effective_from = parse_date(data.get("effective_from"), "effective_from")
    note = (str(data.get("note")).strip() or None) if data.get("note") is not None else None

    locked = locked_through()
    if locked is not None and effective_from <= locked:
        raise ValidationError(
            f"effective_from must be after {locked.isoformat()} — earlier months have approved interest."
        )
    draft = InterestPeriod.query.filter(InterestPeriod.status == PERIOD_DRAFT).first()
    if draft is not None and effective_from <= draft.period_end:
        raise Conflict(
            f"There is a draft interest calculation for {draft.label} that this rate change would affect. "
            "Discard or approve it first."
        )
    if InterestRate.query.filter(InterestRate.effective_from == effective_from).first():
        raise Conflict(f"A rate is already set to take effect on {effective_from.isoformat()}.")

    row = InterestRate(rate_percent=rate, effective_from=effective_from, note=note, set_by=actor)
    db.session.add(row)
    db.session.flush()
    create_audit_log(
        "SET_INTEREST_RATE", target_type="interest_rate", target_id=row.id,
        description=f"{rate}% p.a. from {effective_from.isoformat()}", new_value=row.to_dict(),
    )
    db.session.commit()
    return row


def _rate_lookup(start: date, end: date):
    """Returns rate_for(day) -> Decimal percent; raises if any day has no rate."""
    rates = (
        InterestRate.query.filter(InterestRate.effective_from <= end)
        .order_by(InterestRate.effective_from.asc())
        .all()
    )
    if not rates or rates[0].effective_from > start:
        raise ValidationError(
            f"No interest rate is in effect on {start.isoformat()}. Set a rate effective on or before that date."
        )
    schedule = [(r.effective_from, Decimal(r.rate_percent)) for r in rates]

    def rate_for(day: date) -> Decimal:
        current = schedule[0][1]
        for effective_from, pct in schedule:
            if effective_from <= day:
                current = pct
            else:
                break
        return current

    return rate_for


# ── Calculation ───────────────────────────────────────────────────────────


def compute_payouts(start: date, end: date) -> list[PayoutCalc]:
    """Pure calculation for [start, end] from the current ledger. Investors who
    earned nothing (zero balance all month) are omitted."""
    rate_for = _rate_lookup(start, end)
    days = (end - start).days + 1
    daily_factor = {
        start + timedelta(days=i): rate_for(start + timedelta(days=i)) / HUNDRED / DAY_COUNT for i in range(days)
    }

    results = []
    for investor_id, events in balance_events(None, end).items():
        opening = sum((amt for d, amt in events if d < start), ZERO)
        by_day = defaultdict(Decimal)
        for d, amt in events:
            if d >= start:
                by_day[d] += amt

        balance = opening
        balance_days = ZERO
        interest = Decimal(0)
        for i in range(days):
            day = start + timedelta(days=i)
            balance += by_day.get(day, ZERO)
            balance_days += balance
            interest += balance * daily_factor[day]

        calc = PayoutCalc(
            investor_id=investor_id,
            days=days,
            opening_balance=opening,
            closing_balance=balance,
            balance_days=balance_days,
            gross_unrounded=interest,
        )
        if calc.gross > 0:
            results.append(calc)
    results.sort(key=lambda c: c.investor_id)
    return results


def _validate_month(year: int, month: int) -> tuple[date, date]:
    if not (1 <= month <= 12) or year < 2000:
        raise ValidationError("Provide a valid year and month.")
    start, end = month_bounds(year, month)
    if end >= today_eat():
        raise ValidationError(f"{start.strftime('%B %Y')} hasn't ended yet. Interest is calculated after month-end.")

    existing = InterestPeriod.query.filter(InterestPeriod.period_start == start).first()
    if existing is not None and existing.status in LOCKED_PERIOD_STATUSES:
        raise Conflict(f"Interest for {existing.label} has already been approved.")

    other_draft = InterestPeriod.query.filter(
        InterestPeriod.status == PERIOD_DRAFT, InterestPeriod.period_start != start
    ).first()
    if other_draft is not None:
        raise Conflict(f"There is already a draft for {other_draft.label}. Approve or discard it first.")

    locked = locked_through()
    if locked is not None:
        expected_start = locked + timedelta(days=1)
        if start != expected_start:
            raise ValidationError(
                f"Months must be processed in order. The next month to calculate is "
                f"{expected_start.strftime('%B %Y')}."
            )
    return start, end


def calculate_period(data: dict, actor: str) -> InterestPeriod:
    try:
        year, month = int(data.get("year")), int(data.get("month"))
    except (TypeError, ValueError):
        raise ValidationError("year and month are required.")
    start, end = _validate_month(year, month)
    calcs = compute_payouts(start, end)

    period = InterestPeriod.query.filter(InterestPeriod.period_start == start).first()
    recalculated = period is not None
    if period is None:
        period = InterestPeriod(period_start=start, period_end=end, calculated_by=actor)
        db.session.add(period)
    else:
        period.payouts.delete()
        period.calculated_by = actor
        period.calculated_at = utcnow()

    tax_rate = DEFAULT_TAX_RATE_PERCENT
    period.tax_rate_percent = tax_rate
    period.status = PERIOD_DRAFT
    db.session.flush()

    branch_of = dict(db.session.query(Investor.id, Investor.branch_id)
                     .filter(Investor.id.in_([c.investor_id for c in calcs])).all()) if calcs else {}
    total_gross = total_tax = ZERO
    for c in calcs:
        tax = round_money(c.gross * tax_rate / HUNDRED)
        db.session.add(InterestPayout(
            period_id=period.id,
            investor_id=c.investor_id,
            branch_id=branch_of[c.investor_id],
            days=c.days,
            opening_balance=c.opening_balance,
            closing_balance=c.closing_balance,
            average_daily_balance=c.average_daily_balance,
            rate_percent=c.effective_rate_percent,
            gross_interest=c.gross,
            tax_rate_percent=tax_rate,
            tax_amount=tax,
            net_interest=c.gross - tax,
            status=PAYOUT_PENDING,
        ))
        total_gross += c.gross
        total_tax += tax

    period.investor_count = len(calcs)
    period.total_gross = total_gross
    period.total_tax = total_tax
    period.total_net = total_gross - total_tax

    create_audit_log(
        "RECALCULATE_INTEREST" if recalculated else "CALCULATE_INTEREST",
        target_type="interest_period", target_id=period.id, target_name=period.label,
        description=f"{len(calcs)} investors, gross {fmt_kes(total_gross)}",
    )
    db.session.commit()
    return period


def get_period(period_id: int) -> InterestPeriod:
    period = db.session.get(InterestPeriod, period_id)
    if period is None:
        raise NotFound("Interest period not found.")
    return period


def discard_draft(period_id: int, actor: str) -> None:
    period = get_period(period_id)
    if period.status != PERIOD_DRAFT:
        raise Conflict("Only a draft can be discarded.")
    label = period.label
    db.session.delete(period)
    create_audit_log("DISCARD_INTEREST_DRAFT", target_type="interest_period", target_id=period_id, target_name=label)
    db.session.commit()


def approve_period(period_id: int, actor: str) -> InterestPeriod:
    period = db.session.query(InterestPeriod).filter(InterestPeriod.id == period_id).with_for_update().first()
    if period is None:
        raise NotFound("Interest period not found.")
    if period.status != PERIOD_DRAFT:
        raise Conflict(f"{period.label} has already been {period.status}.")
    assert_can_decide(
        "interest.approve", maker_email=period.calculated_by, actor_email=actor,
        amount=Decimal(period.total_gross), branch_id=None,
        maker_message="Maker-checker: interest must be approved by a different admin from the one who calculated it.",
    )

    # Re-run against the live ledger; refuse if anything moved since the draft.
    fresh = {c.investor_id: c.gross for c in compute_payouts(period.period_start, period.period_end)}
    stored = {p.investor_id: Decimal(p.gross_interest) for p in period.payouts}
    if fresh != stored:
        raise Conflict(
            f"Transactions affecting {period.label} changed after this draft was calculated. "
            "Recalculate and review the draft again before approving."
        )

    period.status = PERIOD_APPROVED
    period.approved_by = actor
    period.approved_at = utcnow()
    payouts = period.payouts.all()
    db.session.flush()  # each statement PDF must see the month as approved
    for payout in payouts:
        queue_interest_statement(payout, actor)
    if not payouts:
        # Nothing to pay — the month is approved and immediately settled.
        period.status = PERIOD_PAID
        period.paid_at = utcnow()

    create_audit_log(
        "APPROVE_INTEREST", target_type="interest_period", target_id=period.id, target_name=period.label,
        description=f"{len(payouts)} statements queued, net {fmt_kes(period.total_net)}",
    )
    db.session.commit()
    return period


def mark_payouts_paid(period_id: int, data: dict, actor: str) -> InterestPeriod:
    """data = {"payments": [{"payout_id": 1, "reference": "QX12..."}, ...]}"""
    period = db.session.query(InterestPeriod).filter(InterestPeriod.id == period_id).with_for_update().first()
    if period is None:
        raise NotFound("Interest period not found.")
    if period.status != PERIOD_APPROVED:
        raise Conflict("Payouts can only be marked paid on an approved period that isn't fully paid yet.")

    payments = data.get("payments")
    if not isinstance(payments, list) or not payments:
        raise ValidationError("payments must be a non-empty list of {payout_id, reference}.")

    now = utcnow()
    marked = []
    for item in payments:
        try:
            payout_id = int(item.get("payout_id"))
        except (TypeError, ValueError, AttributeError):
            raise ValidationError("Each payment needs a payout_id.")
        reference = str(item.get("reference") or "").strip()
        if not reference:
            raise ValidationError(f"Payout {payout_id}: a payment reference is required.")
        if len(reference) > 100:
            raise ValidationError(f"Payout {payout_id}: reference is too long.")

        payout = db.session.get(InterestPayout, payout_id)
        if payout is None or payout.period_id != period.id:
            raise NotFound(f"Payout {payout_id} is not part of {period.label}.")
        if payout.status == PAYOUT_PAID:
            raise Conflict(f"Payout {payout_id} ({payout.investor.client_code}) is already marked paid.")
        payout.status = PAYOUT_PAID
        payout.payment_reference = reference
        payout.paid_at = now
        payout.paid_by = actor
        marked.append({"payout_id": payout.id, "client_code": payout.investor.client_code,
                       "net_interest": as_str(payout.net_interest), "reference": reference})

    db.session.flush()
    remaining = period.payouts.filter(InterestPayout.status == PAYOUT_PENDING).count()
    if remaining == 0:
        period.status = PERIOD_PAID
        period.paid_at = now

    create_audit_log(
        "MARK_INTEREST_PAID", target_type="interest_period", target_id=period.id, target_name=period.label,
        description=f"{len(marked)} payouts marked paid; {remaining} outstanding", new_value=marked,
    )
    db.session.commit()
    return period


def period_payouts(period: InterestPeriod) -> list[InterestPayout]:
    return (
        period.payouts.join(Investor, Investor.id == InterestPayout.investor_id)
        .order_by(Investor.client_code.asc())
        .all()
    )


def outstanding_payout_total() -> Decimal:
    total = (
        db.session.query(func.coalesce(func.sum(InterestPayout.net_interest), 0))
        .join(InterestPeriod, InterestPeriod.id == InterestPayout.period_id)
        .filter(InterestPayout.status == PAYOUT_PENDING, InterestPeriod.status == PERIOD_APPROVED)
        .scalar()
    )
    return Decimal(total)
