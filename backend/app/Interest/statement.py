"""
Assembles everything an interest statement shows (PDF attachment and the
in-app statement view) for one payout.
"""
from decimal import Decimal

from sqlalchemy import func

from app.database.database import db
from app.Interest.model import LOCKED_PERIOD_STATUSES, InterestPayout, InterestPeriod
from app.Transactions.ledger import _deposits_total, _withdrawals_total, investor_totals, ledger_entries
from app.utils.dates import today_eat
from app.utils.http import NotFound


def mask_account(value: str | None) -> str | None:
    if not value:
        return None
    tail = value[-4:]
    return f"{'•' * max(len(value) - 4, 0)}{tail}" if len(value) > 4 else value


def build_interest_statement_data(payout_id: int) -> dict:
    payout = db.session.get(InterestPayout, payout_id)
    if payout is None:
        raise NotFound("Payout not found.")
    period = payout.period
    investor = payout.investor
    end = period.period_end

    ledger = ledger_entries(investor.id, period.period_start, end)

    interest_to_date = (
        db.session.query(func.coalesce(func.sum(InterestPayout.net_interest), 0))
        .join(InterestPeriod, InterestPeriod.id == InterestPayout.period_id)
        .filter(
            InterestPayout.investor_id == investor.id,
            InterestPeriod.period_end <= end,
            InterestPeriod.status.in_(LOCKED_PERIOD_STATUSES),
        )
        .scalar()
    )

    return {
        "investor": {
            "full_name": investor.full_name,
            "client_code": investor.client_code,
            "email": investor.email,
            "payout_method": investor.payout_method,
            "bank_name": investor.bank_name,
            "payout_account": mask_account(investor.payout_account),
        },
        "period": {
            "label": period.label,
            "start": period.period_start,
            "end": end,
            "status": period.status,
        },
        "payout": {
            "id": payout.id,
            "days": payout.days,
            "opening_balance": Decimal(payout.opening_balance),
            "closing_balance": Decimal(payout.closing_balance),
            "average_daily_balance": Decimal(payout.average_daily_balance),
            "rate_percent": Decimal(payout.rate_percent),
            "gross_interest": Decimal(payout.gross_interest),
            "tax_rate_percent": Decimal(payout.tax_rate_percent),
            "tax_amount": Decimal(payout.tax_amount),
            "net_interest": Decimal(payout.net_interest),
            "status": payout.status,
            "paid_at": payout.paid_at,
            "payment_reference": payout.payment_reference,
        },
        "ledger": ledger,
        "to_date": {
            "total_deposited": _deposits_total(investor.id, end),
            "total_withdrawn": _withdrawals_total(investor.id, end),
            "interest_paid_to_date": Decimal(interest_to_date),
        },
    }


def build_account_statement_data(investor_id: int) -> dict:
    """Everything an on-demand "as of today" account statement shows."""
    from app.Interest.service import current_rate
    from app.Investors.model import Investor

    investor = db.session.get(Investor, investor_id)
    if investor is None:
        raise NotFound("Investor not found.")
    payouts = (
        InterestPayout.query.join(InterestPeriod, InterestPeriod.id == InterestPayout.period_id)
        .filter(InterestPayout.investor_id == investor.id, InterestPeriod.status.in_(LOCKED_PERIOD_STATUSES))
        .order_by(InterestPeriod.period_start.asc())
        .all()
    )
    rate = current_rate()
    return {
        "statement_type": "account",
        "as_of": today_eat(),
        "investor": {
            "full_name": investor.full_name,
            "client_code": investor.client_code,
            "email": investor.email,
            "payout_method": investor.payout_method,
            "bank_name": investor.bank_name,
            "payout_account": mask_account(investor.payout_account),
        },
        "totals": investor_totals(investor.id),
        "rate_percent": Decimal(rate.rate_percent) if rate else None,
        "ledger": ledger_entries(investor.id),
        "payouts": [
            {
                "label": p.period.label,
                "average_daily_balance": Decimal(p.average_daily_balance),
                "rate_percent": Decimal(p.rate_percent),
                "net_interest": Decimal(p.net_interest),
                "status": p.status,
                "paid_at": p.paid_at,
            }
            for p in payouts
        ],
    }
