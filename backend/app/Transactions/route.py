from flask import Blueprint, request
from sqlalchemy import or_

from app.auth import actor_email, requires
from app.Emails.model import EMAIL_DEPOSIT_REVERSAL, OutboxEmail
from app.Investors.model import Investor
from app.Transactions import service
from app.Transactions.model import Deposit, Withdrawal
from app.utils.dates import parse_date
from app.utils.http import ok, page_args, paginate

transactions_v1 = Blueprint("transactions_v1", __name__)


def _search(query, model):
    term = (request.args.get("search") or "").strip()
    if term:
        like = f"%{term}%"
        query = query.join(Investor, Investor.id == model.investor_id).filter(
            or_(Investor.full_name.ilike(like), Investor.client_code.ilike(like), Investor.email.ilike(like))
        )
    return query


# ── Deposits ──


@transactions_v1.get("/api/v1/deposits")
@requires("deposit.view")
def list_deposits():
    page, per_page = page_args(request.args)
    q = _search(Deposit.query, Deposit)
    if request.args.get("status"):
        q = q.filter(Deposit.status == request.args["status"])
    if request.args.get("investor_id"):
        q = q.filter(Deposit.investor_id == int(request.args["investor_id"]))
    start = parse_date(request.args.get("from"), "from", required=False)
    end = parse_date(request.args.get("to"), "to", required=False)
    if start:
        q = q.filter(Deposit.value_date >= start)
    if end:
        q = q.filter(Deposit.value_date <= end)
    q = q.order_by(Deposit.value_date.desc(), Deposit.id.desc())
    return ok(paginate(q, page, per_page, lambda d: d.to_dict()))


@transactions_v1.post("/api/v1/deposits")
@requires("deposit.record")
def record_deposit():
    deposit = service.record_deposit(request.get_json(silent=True) or {}, actor_email())
    return ok(deposit.to_dict(), "Deposit recorded. A confirmation email has been queued to the investor.", 201)


@transactions_v1.post("/api/v1/deposits/<int:deposit_id>/reverse")
@requires("deposit.reverse")
def reverse_deposit(deposit_id):
    deposit = service.reverse_deposit(deposit_id, request.get_json(silent=True) or {}, actor_email())
    notified = OutboxEmail.query.filter_by(deposit_id=deposit.id, email_type=EMAIL_DEPOSIT_REVERSAL).first()
    return ok(deposit.to_dict(), "Deposit reversed. A reversal notice has been queued to the investor."
              if notified else "Deposit reversed.")


# ── Withdrawals ──


@transactions_v1.get("/api/v1/withdrawals")
@requires("withdrawal.view")
def list_withdrawals():
    page, per_page = page_args(request.args)
    q = _search(Withdrawal.query, Withdrawal)
    if request.args.get("status"):
        q = q.filter(Withdrawal.status == request.args["status"])
    if request.args.get("investor_id"):
        q = q.filter(Withdrawal.investor_id == int(request.args["investor_id"]))
    q = q.order_by(Withdrawal.created_at.desc())
    return ok(paginate(q, page, per_page, lambda w: w.to_dict()))


@transactions_v1.post("/api/v1/withdrawals")
@requires("withdrawal.request")
def request_withdrawal():
    withdrawal = service.request_withdrawal(request.get_json(silent=True) or {}, actor_email())
    return ok(withdrawal.to_dict(), "Withdrawal recorded and awaiting approval by an admin.", 201)


@transactions_v1.post("/api/v1/withdrawals/<int:withdrawal_id>/approve")
@requires("withdrawal.approve")
def approve_withdrawal(withdrawal_id):
    withdrawal = service.approve_withdrawal(withdrawal_id, request.get_json(silent=True) or {}, actor_email())
    return ok(withdrawal.to_dict(), "Withdrawal approved. A confirmation email has been queued to the investor.")


@transactions_v1.post("/api/v1/withdrawals/<int:withdrawal_id>/reject")
@requires("withdrawal.approve")
def reject_withdrawal(withdrawal_id):
    withdrawal = service.reject_withdrawal(withdrawal_id, request.get_json(silent=True) or {}, actor_email())
    return ok(withdrawal.to_dict(), "Withdrawal rejected.")
