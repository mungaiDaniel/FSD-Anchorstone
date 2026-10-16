"""
Money handling. All amounts are KES, stored as NUMERIC(20,2) and handled as
Decimal end to end — never float — so balances and interest reconcile to the
cent.
"""
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from app.utils.http import ValidationError

CENT = Decimal("0.01")
ZERO = Decimal("0.00")


def round_money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def parse_amount(value, field: str = "amount") -> Decimal:
    """A strictly positive amount with at most 2 decimal places."""
    if value in (None, ""):
        raise ValidationError(f"{field} is required.")
    try:
        amount = Decimal(str(value).replace(",", "").strip())
    except InvalidOperation:
        raise ValidationError(f"{field} must be a number.")
    if not amount.is_finite() or amount <= 0:
        raise ValidationError(f"{field} must be greater than zero.")
    if amount != amount.quantize(CENT):
        raise ValidationError(f"{field} cannot have more than 2 decimal places.")
    if amount >= Decimal("1e18"):
        raise ValidationError(f"{field} is too large.")
    return amount


def parse_rate_percent(value, field: str = "rate_percent") -> Decimal:
    """An annual rate in percent, e.g. 12.5 for 12.5% p.a."""
    if value in (None, ""):
        raise ValidationError(f"{field} is required.")
    try:
        rate = Decimal(str(value).strip())
    except InvalidOperation:
        raise ValidationError(f"{field} must be a number.")
    if not rate.is_finite() or rate < 0 or rate > 100:
        raise ValidationError(f"{field} must be between 0 and 100.")
    if rate != rate.quantize(Decimal("0.0001")):
        raise ValidationError(f"{field} cannot have more than 4 decimal places.")
    return rate


def fmt_kes(value) -> str:
    return f"KES {Decimal(value or 0):,.2f}"


def as_str(value) -> str | None:
    """Serialize a Decimal for JSON without float rounding."""
    if value is None:
        return None
    return f"{Decimal(value):.2f}"
