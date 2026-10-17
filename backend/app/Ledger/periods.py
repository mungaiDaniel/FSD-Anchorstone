"""
Accounting periods: one per calendar month, open or closed.

A period row is created the first time something is posted into its month,
or when it is closed. Its financial year is fixed then, from the setting
gl.financial_year_end_month in force on the period's last day (default 12:
the year ends on 31 December). Nothing may be posted into a closed period,
and no new period may be opened at or before the latest closed one; the
database enforces both. Closing is the gl.period.close change request;
reopening is gl.period.reopen (a reason and two approvers).
"""
import re
from datetime import date

from sqlalchemy.dialects.postgresql import insert

from app.database.database import db
from app.Ledger.model import PERIOD_CLOSED, PERIOD_OPEN, GlPeriod
from app.Settings import business
from app.utils.dates import month_bounds
from app.utils.http import NotFound, ValidationError


def bounds(d: date) -> tuple[date, date]:
    return month_bounds(d.year, d.month)


def financial_year_for(period_end: date) -> int:
    end_month = business.get("gl.financial_year_end_month", as_of=period_end)
    return period_end.year if period_end.month <= end_month else period_end.year + 1


def parse_label(value) -> date:
    """'2026-09' -> date(2026, 9, 1)."""
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}", value.strip()):
        raise ValidationError("period must look like 2026-09.")
    year, month = (int(p) for p in value.strip().split("-"))
    if not 1 <= month <= 12 or year < 2000:
        raise ValidationError("period must be a real month (YYYY-MM).")
    return date(year, month, 1)


def find(start: date) -> GlPeriod | None:
    return GlPeriod.query.filter(GlPeriod.period_start == start).first()


def get_period(period_id) -> GlPeriod:
    period = db.session.get(GlPeriod, period_id) if isinstance(period_id, int) else None
    if period is None:
        raise NotFound("GL period not found.")
    return period


def latest_closed() -> GlPeriod | None:
    return (GlPeriod.query.filter(GlPeriod.status == PERIOD_CLOSED)
            .order_by(GlPeriod.period_start.desc()).first())


def list_periods() -> list[GlPeriod]:
    return GlPeriod.query.order_by(GlPeriod.period_start.desc()).all()


def ensure_period(d: date, actor_email: str) -> GlPeriod:
    """The period for d's month, opening it if it doesn't exist yet (safe under concurrency)."""
    start, end = bounds(d)
    period = find(start)
    if period is not None:
        return period
    closed = latest_closed()
    if closed is not None and closed.period_start > start:
        raise ValidationError(f"{start:%Y-%m} is before the latest closed GL period ({closed.label}); "
                              "nothing can be posted there.")
    db.session.execute(insert(GlPeriod.__table__).values(
        period_start=start, period_end=end, financial_year=financial_year_for(end), status=PERIOD_OPEN,
        reopen_count=0, created_by=actor_email,
    ).on_conflict_do_nothing(index_elements=["period_start"]))
    return find(start)


def lock_open(d: date, actor_email: str) -> GlPeriod:
    """The open period for d, share-locked so it can't be closed until this transaction ends."""
    period = ensure_period(d, actor_email)
    period = (db.session.query(GlPeriod).filter(GlPeriod.id == period.id)
              .with_for_update(read=True).populate_existing().one())
    if period.status != PERIOD_OPEN:
        raise ValidationError(f"GL period {period.label} is closed; nothing can be posted into it.")
    return period


def is_open(d: date) -> bool:
    period = find(bounds(d)[0])
    if period is not None:
        return period.status == PERIOD_OPEN
    closed = latest_closed()
    return closed is None or closed.period_start < bounds(d)[0]
