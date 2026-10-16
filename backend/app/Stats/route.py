"""Dashboard numbers for the Overview page."""
from datetime import date
from decimal import Decimal

from flask import Blueprint
from sqlalchemy import func

from app.auth import requires
from app.database.database import db
from app.Emails.model import STATUS_FAILED, STATUS_PENDING, STATUS_QUEUED, OutboxEmail
from app.Interest.model import LOCKED_PERIOD_STATUSES, PERIOD_DRAFT, InterestPeriod
from app.Interest.service import current_rate, outstanding_payout_total
from app.Investors.model import Investor
from app.Transactions.ledger import balances_subquery
from app.Transactions.model import DEPOSIT_POSTED, WITHDRAWAL_APPROVED, WITHDRAWAL_PENDING, Deposit, Withdrawal
from app.utils.dates import iso, today_eat
from app.utils.http import ok
from app.utils.money import as_str

stats_v1 = Blueprint("stats_v1", __name__)


def _month_start(d: date, months_back: int = 0) -> date:
    y, m = d.year, d.month - months_back
    while m <= 0:
        m += 12
        y -= 1
    return date(y, m, 1)


@stats_v1.get("/api/v1/stats/overview")
@requires("stats.view")
def overview():
    today = today_eat()
    month_start = _month_start(today)

    bal = balances_subquery()
    total_balance = db.session.query(func.coalesce(func.sum(bal.c.balance), 0)).scalar()
    active = db.session.query(func.count(Investor.id)).filter(Investor.status == "active").scalar()
    funded = db.session.query(func.count()).select_from(bal).filter(bal.c.balance > 0).scalar()

    def _sum(model, status, start, end=None):
        q = db.session.query(func.coalesce(func.sum(model.amount), 0)).filter(
            model.status == status, model.value_date >= start)
        if end:
            q = q.filter(model.value_date < end)
        return Decimal(q.scalar())

    pending_count, pending_total = db.session.query(
        func.count(Withdrawal.id), func.coalesce(func.sum(Withdrawal.amount), 0)
    ).filter(Withdrawal.status == WITHDRAWAL_PENDING).one()

    # Six-month deposits vs withdrawals chart, oldest first.
    flows = []
    for back in range(5, -1, -1):
        start = _month_start(today, back)
        end = _month_start(today, back - 1) if back > 0 else None
        flows.append({
            "month": start.strftime("%b %Y"),
            "deposits": as_str(_sum(Deposit, DEPOSIT_POSTED, start, end)),
            "withdrawals": as_str(_sum(Withdrawal, WITHDRAWAL_APPROVED, start, end)),
        })

    last_period = (InterestPeriod.query.filter(InterestPeriod.status.in_(LOCKED_PERIOD_STATUSES))
                   .order_by(InterestPeriod.period_start.desc()).first())
    draft = InterestPeriod.query.filter(InterestPeriod.status == PERIOD_DRAFT).first()
    rate = current_rate()
    email_counts = dict(db.session.query(OutboxEmail.status, func.count())
                        .filter(OutboxEmail.status.in_([STATUS_QUEUED, STATUS_FAILED, STATUS_PENDING]))
                        .group_by(OutboxEmail.status).all())

    return ok({
        "total_balance": as_str(total_balance),
        "active_investors": active,
        "funded_investors": funded,
        "deposits_this_month": as_str(_sum(Deposit, DEPOSIT_POSTED, month_start)),
        "withdrawals_this_month": as_str(_sum(Withdrawal, WITHDRAWAL_APPROVED, month_start)),
        "pending_withdrawals": {"count": pending_count, "total": as_str(pending_total)},
        "current_rate": rate.to_dict() if rate else None,
        "interest_outstanding": as_str(outstanding_payout_total()),
        "last_period": last_period.to_dict() if last_period else None,
        "draft_period": draft.to_dict() if draft else None,
        "emails": {"queued": email_counts.get(STATUS_QUEUED, 0), "failed": email_counts.get(STATUS_FAILED, 0),
                   "pending": email_counts.get(STATUS_PENDING, 0)},
        "monthly_flows": flows,
        "as_of": iso(today),
    })
