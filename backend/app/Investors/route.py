from flask import Blueprint, request

from app.auth import actor_email, requires
from app.Emails.model import OutboxEmail
from app.Interest.model import LOCKED_PERIOD_STATUSES, InterestPayout, InterestPeriod
from app.Investors import service
from app.Transactions.ledger import ledger_entries
from app.Transactions.model import Deposit, Withdrawal
from app.utils.dates import iso, parse_date
from app.utils.http import ok, page_args
from app.utils.money import as_str

investors_v1 = Blueprint("investors_v1", __name__)


@investors_v1.get("/api/v1/investors")
@requires("investor.view")
def list_investors():
    page, per_page = page_args(request.args)
    return ok(service.list_investors(request.args.get("search"), request.args.get("status"), page, per_page))


@investors_v1.post("/api/v1/investors")
@requires("investor.create")
def create_investor():
    investor = service.create_investor(request.get_json(silent=True) or {}, actor_email())
    return ok(service.investor_summary(investor), f"Investor {investor.client_code} created.", 201)


@investors_v1.get("/api/v1/investors/<int:investor_id>")
@requires("investor.view")
def get_investor(investor_id):
    return ok(service.investor_summary(service.get_investor(investor_id)))


@investors_v1.patch("/api/v1/investors/<int:investor_id>")
@requires("investor.edit")
def update_investor(investor_id):
    investor = service.update_investor(investor_id, request.get_json(silent=True) or {}, actor_email())
    return ok(service.investor_summary(investor), "Investor updated.")


@investors_v1.patch("/api/v1/investors/<int:investor_id>/status")
@requires("investor.close")
def set_status(investor_id):
    investor = service.set_investor_status(investor_id, request.get_json(silent=True) or {}, actor_email())
    return ok(service.investor_summary(investor), f"Account {investor.status}.")


@investors_v1.get("/api/v1/investors/<int:investor_id>/ledger")
@requires("investor.view")
def investor_ledger(investor_id):
    service.get_investor(investor_id)
    start = parse_date(request.args.get("from"), "from", required=False)
    end = parse_date(request.args.get("to"), "to", required=False)
    ledger = ledger_entries(investor_id, start, end)
    entries = [{**e, "date": iso(e["date"]), "amount": as_str(e["amount"]), "balance": as_str(e["balance"])}
               for e in reversed(ledger["entries"])]
    return ok({"opening_balance": as_str(ledger["opening_balance"]),
               "closing_balance": as_str(ledger["closing_balance"]),
               "entries": entries})


@investors_v1.get("/api/v1/investors/<int:investor_id>/deposits")
@requires("investor.view")
def investor_deposits(investor_id):
    service.get_investor(investor_id)
    rows = Deposit.query.filter(Deposit.investor_id == investor_id).order_by(
        Deposit.value_date.desc(), Deposit.id.desc()).all()
    return ok([d.to_dict() for d in rows])


@investors_v1.get("/api/v1/investors/<int:investor_id>/withdrawals")
@requires("investor.view")
def investor_withdrawals(investor_id):
    service.get_investor(investor_id)
    rows = Withdrawal.query.filter(Withdrawal.investor_id == investor_id).order_by(
        Withdrawal.created_at.desc()).all()
    return ok([w.to_dict() for w in rows])


@investors_v1.get("/api/v1/investors/<int:investor_id>/payouts")
@requires("investor.view")
def investor_payouts(investor_id):
    service.get_investor(investor_id)
    rows = (
        InterestPayout.query.join(InterestPeriod, InterestPeriod.id == InterestPayout.period_id)
        .filter(InterestPayout.investor_id == investor_id, InterestPeriod.status.in_(LOCKED_PERIOD_STATUSES))
        .order_by(InterestPeriod.period_start.desc())
        .all()
    )
    return ok([p.to_dict() for p in rows])


@investors_v1.get("/api/v1/investors/<int:investor_id>/emails")
@requires("investor.view")
def investor_emails(investor_id):
    service.get_investor(investor_id)
    rows = OutboxEmail.query.filter(OutboxEmail.investor_id == investor_id).order_by(
        OutboxEmail.queued_at.desc()).limit(200).all()
    return ok([e.to_dict() for e in rows])
