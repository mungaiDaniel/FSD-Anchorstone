"""
Business rules for deposits and withdrawals.

Deposits
  - recorded by any staff member, posted immediately, confirmation emailed automatically
  - value date: not in the future, not inside an approved interest period
  - reference must be unique (stops the same receipt being entered twice)
  - mistakes are reversed by an admin (with a reason), never edited or deleted

Withdrawals (maker-checker)
  - staff records a request → pending; balance is NOT reduced yet
  - a different admin approves → balance reduced from the value date, confirmation emailed
  - or a different admin rejects it (with a reason)
  - a request can't exceed the available balance (balance − other pending requests),
    and approval re-checks that no day from the value date onward would go negative
"""
from decimal import Decimal

from sqlalchemy import func

from app.database.database import db
from app.Emails.composer import queue_deposit_confirmation, queue_withdrawal_confirmation
from app.Emails.model import STATUS_CANCELLED, STATUS_QUEUED, OutboxEmail
from app.Transactions.ledger import (
    assert_not_locked,
    balance_as_of,
    lock_investor,
    min_balance_from,
    pending_withdrawals_total,
)
from app.Transactions.model import (
    DEPOSIT_POSTED,
    DEPOSIT_REVERSED,
    PAYMENT_METHODS,
    WITHDRAWAL_APPROVED,
    WITHDRAWAL_PENDING,
    WITHDRAWAL_REJECTED,
    Deposit,
    Withdrawal,
)
from app.utils.audit_log import create_audit_log
from app.utils.dates import parse_date, today_eat, utcnow
from app.utils.http import Conflict, Forbidden, NotFound, ValidationError
from app.utils.money import as_str, fmt_kes, parse_amount


def _method(value) -> str:
    method = str(value or "").strip().lower()
    if method not in PAYMENT_METHODS:
        raise ValidationError(f"method must be one of: {', '.join(PAYMENT_METHODS)}.")
    return method


def _not_future(d, field: str):
    if d > today_eat():
        raise ValidationError(f"{field} cannot be in the future.")


def _text(value, max_len: int | None = None) -> str | None:
    text = str(value).strip() if value is not None else ""
    if max_len and len(text) > max_len:
        raise ValidationError(f"Value is too long (max {max_len} characters).")
    return text or None


# ── Deposits ──────────────────────────────────────────────────────────────


def record_deposit(data: dict, actor: str) -> Deposit:
    try:
        investor_id = int(data.get("investor_id"))
    except (TypeError, ValueError):
        raise ValidationError("investor_id is required.")
    amount = parse_amount(data.get("amount"))
    value_date = parse_date(data.get("value_date"), "value_date")
    method = _method(data.get("method"))
    reference = _text(data.get("reference"), 100)
    if not reference:
        raise ValidationError("reference is required (bank / M-Pesa / cheque reference).")
    notes = _text(data.get("notes"))

    _not_future(value_date, "value_date")
    assert_not_locked(value_date, "A deposit")

    investor = lock_investor(investor_id)
    if investor.status != "active":
        raise ValidationError("Deposits can only be recorded for active investors.")
    if db.session.query(Deposit.id).filter(func.lower(Deposit.reference) == reference.lower()).first():
        raise Conflict(f"A deposit with reference '{reference}' has already been recorded.")

    deposit = Deposit(
        investor_id=investor.id,
        amount=amount,
        value_date=value_date,
        method=method,
        reference=reference,
        notes=notes,
        status=DEPOSIT_POSTED,
        recorded_by=actor,
    )
    db.session.add(deposit)
    db.session.flush()
    queue_deposit_confirmation(deposit, actor)
    db.session.commit()

    create_audit_log(
        "RECORD_DEPOSIT", target_type="deposit", target_id=deposit.id, target_name=investor.client_code,
        description=f"{fmt_kes(amount)} on {value_date.isoformat()} ({reference})",
        new_value=deposit.to_dict(),
    )
    return deposit


def reverse_deposit(deposit_id: int, data: dict, actor: str) -> Deposit:
    reason = _text(data.get("reason"))
    if not reason:
        raise ValidationError("A reason is required to reverse a deposit.")

    deposit = db.session.get(Deposit, deposit_id)
    if deposit is None:
        raise NotFound("Deposit not found.")
    lock_investor(deposit.investor_id)
    db.session.refresh(deposit)
    if deposit.status != DEPOSIT_POSTED:
        raise Conflict("This deposit has already been reversed.")

    assert_not_locked(deposit.value_date, "This deposit")
    lowest = min_balance_from(deposit.investor_id, deposit.value_date)
    if lowest - Decimal(deposit.amount) < 0:
        raise Conflict(
            "Reversing this deposit would make the account balance negative, because later withdrawals "
            "relied on it. Resolve those withdrawals first."
        )

    deposit.status = DEPOSIT_REVERSED
    deposit.reversed_by = actor
    deposit.reversed_at = utcnow()
    deposit.reversal_reason = reason

    # If the confirmation email hasn't gone out yet, don't send it.
    db.session.query(OutboxEmail).filter(
        OutboxEmail.deposit_id == deposit.id, OutboxEmail.status == STATUS_QUEUED
    ).update({"status": STATUS_CANCELLED, "last_error": "Deposit reversed before sending."})
    db.session.commit()

    create_audit_log(
        "REVERSE_DEPOSIT", target_type="deposit", target_id=deposit.id,
        target_name=deposit.investor.client_code, description=reason,
        old_value={"status": DEPOSIT_POSTED}, new_value={"status": DEPOSIT_REVERSED, "reason": reason},
    )
    return deposit


# ── Withdrawals ───────────────────────────────────────────────────────────


def request_withdrawal(data: dict, actor: str) -> Withdrawal:
    try:
        investor_id = int(data.get("investor_id"))
    except (TypeError, ValueError):
        raise ValidationError("investor_id is required.")
    amount = parse_amount(data.get("amount"))
    requested_date = parse_date(data.get("requested_date"), "requested_date", required=False) or today_eat()
    _not_future(requested_date, "requested_date")
    method = _method(data.get("method"))
    notes = _text(data.get("notes"))

    investor = lock_investor(investor_id)
    if investor.status != "active":
        raise ValidationError("Withdrawals can only be requested for active investors.")

    available = balance_as_of(investor.id) - pending_withdrawals_total(investor.id)
    if amount > available:
        raise ValidationError(
            f"Amount exceeds the available balance of {fmt_kes(available)} "
            "(current balance less other pending withdrawals)."
        )

    withdrawal = Withdrawal(
        investor_id=investor.id,
        amount=amount,
        requested_date=requested_date,
        method=method,
        notes=notes,
        status=WITHDRAWAL_PENDING,
        requested_by=actor,
    )
    db.session.add(withdrawal)
    db.session.commit()

    create_audit_log(
        "REQUEST_WITHDRAWAL", target_type="withdrawal", target_id=withdrawal.id,
        target_name=investor.client_code, description=f"{fmt_kes(amount)} requested",
        new_value=withdrawal.to_dict(),
    )
    return withdrawal


def _pending_withdrawal_for_decision(withdrawal_id: int, actor: str) -> Withdrawal:
    withdrawal = db.session.get(Withdrawal, withdrawal_id)
    if withdrawal is None:
        raise NotFound("Withdrawal not found.")
    lock_investor(withdrawal.investor_id)
    db.session.refresh(withdrawal)
    if withdrawal.status != WITHDRAWAL_PENDING:
        raise Conflict(f"This withdrawal has already been {withdrawal.status}.")
    if withdrawal.requested_by.lower() == actor.lower():
        raise Forbidden("Maker-checker: a withdrawal must be approved or rejected by someone other than the person who recorded it.")
    return withdrawal


def approve_withdrawal(withdrawal_id: int, data: dict, actor: str) -> Withdrawal:
    withdrawal = _pending_withdrawal_for_decision(withdrawal_id, actor)

    value_date = parse_date(data.get("value_date"), "value_date", required=False) or today_eat()
    _not_future(value_date, "value_date")
    if value_date < withdrawal.requested_date:
        raise ValidationError("value_date cannot be before the date the withdrawal was requested.")
    assert_not_locked(value_date, "A withdrawal")

    lowest = min_balance_from(withdrawal.investor_id, value_date)
    if lowest - Decimal(withdrawal.amount) < 0:
        raise Conflict(
            f"Insufficient balance: approving {fmt_kes(withdrawal.amount)} effective "
            f"{value_date.isoformat()} would take the balance below zero "
            f"(lowest balance from that date is {fmt_kes(lowest)})."
        )

    withdrawal.status = WITHDRAWAL_APPROVED
    withdrawal.value_date = value_date
    withdrawal.payment_reference = _text(data.get("payment_reference"), 100)
    withdrawal.decided_by = actor
    withdrawal.decided_at = utcnow()
    db.session.flush()
    queue_withdrawal_confirmation(withdrawal, actor)
    db.session.commit()

    create_audit_log(
        "APPROVE_WITHDRAWAL", target_type="withdrawal", target_id=withdrawal.id,
        target_name=withdrawal.investor.client_code,
        description=f"{fmt_kes(withdrawal.amount)} effective {value_date.isoformat()}",
        old_value={"status": WITHDRAWAL_PENDING},
        new_value={"status": WITHDRAWAL_APPROVED, "value_date": value_date.isoformat(),
                   "amount": as_str(withdrawal.amount)},
    )
    return withdrawal


def reject_withdrawal(withdrawal_id: int, data: dict, actor: str) -> Withdrawal:
    reason = _text(data.get("reason"))
    if not reason:
        raise ValidationError("A reason is required to reject a withdrawal.")
    withdrawal = _pending_withdrawal_for_decision(withdrawal_id, actor)

    withdrawal.status = WITHDRAWAL_REJECTED
    withdrawal.rejection_reason = reason
    withdrawal.decided_by = actor
    withdrawal.decided_at = utcnow()
    db.session.commit()

    create_audit_log(
        "REJECT_WITHDRAWAL", target_type="withdrawal", target_id=withdrawal.id,
        target_name=withdrawal.investor.client_code, description=reason,
        old_value={"status": WITHDRAWAL_PENDING}, new_value={"status": WITHDRAWAL_REJECTED},
    )
    return withdrawal
