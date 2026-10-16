"""
Business dates. Anchorstone operates in Nairobi (EAT, UTC+3, no DST), so
"today" for value dates and period checks is the Nairobi calendar date, not
the server's local or UTC date.
"""
import calendar
from datetime import date, datetime, timedelta, timezone

from app.utils.http import ValidationError

EAT = timezone(timedelta(hours=3), name="EAT")


def today_eat() -> date:
    return datetime.now(EAT).date()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def parse_date(value, field: str, *, required: bool = True) -> date | None:
    if value in (None, ""):
        if required:
            raise ValidationError(f"{field} is required (YYYY-MM-DD).")
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        raise ValidationError(f"{field} must be a date in YYYY-MM-DD format.")


def month_bounds(year: int, month: int) -> tuple[date, date]:
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


def iso(value) -> str | None:
    return value.isoformat() if value is not None else None
