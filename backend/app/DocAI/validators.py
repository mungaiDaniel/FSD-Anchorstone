"""
Checks run in Python on every value the model returns (05 §4.2). A failed check
doesn't change the value: the field is stored with validation 'failed' and the
reason, for the reviewer.
"""
import re
from datetime import date
from decimal import Decimal, InvalidOperation

from app.utils.dates import today_eat

KRA_PIN = re.compile(r"[AP]\d{9}[A-Z]")
KENYAN_ID = re.compile(r"\d{7,8}")
TWO_PLACES = Decimal("0.01")


def parse_iso_date(value: str | None) -> date | None:
    if not value or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value.strip()):
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


def parse_money(value: str | None, *, signed: bool = False) -> Decimal | None:
    """A printed amount as Decimal (commas tolerated), or None when it isn't one. Never rounds."""
    if value is None:
        return None
    text = str(value).strip().replace(",", "").replace(" ", "")
    if not re.fullmatch(r"-?\d+(\.\d{1,2})?", text):
        return None
    try:
        number = Decimal(text)
    except InvalidOperation:
        return None
    if number < 0 and not signed:
        return None
    return number.quantize(TWO_PLACES)


def check(kind: str, value: str | None) -> str | None:
    """None when the value passes, else the reason it fails."""
    text = value.strip()
    if kind == "kenyan_id":
        return None if KENYAN_ID.fullmatch(text) else "A Kenyan ID number is 7 or 8 digits."
    if kind == "kra_pin":
        return None if KRA_PIN.fullmatch(text.upper()) else "A KRA PIN is a letter (A or P), 9 digits and a letter."
    if kind == "sex":
        return None if text in ("M", "F") else "Sex must be M or F."
    if kind in ("date", "past_date"):
        parsed = parse_iso_date(text)
        if parsed is None:
            return "Not a valid date (YYYY-MM-DD)."
        if kind == "past_date" and parsed > today_eat():
            return "This date is in the future."
        return None
    if kind in ("money", "signed_money"):
        if parse_money(text, signed=kind == "signed_money") is None:
            return "Not an amount with at most 2 decimal places" + ("." if kind == "signed_money" else
                                                                     " (and not negative).")
        return None
    if kind == "integer":
        return None if re.fullmatch(r"-?\d+", text.replace(",", "")) else "Not a whole number."
    if kind == "year":
        if not re.fullmatch(r"\d{4}", text) or not 1900 <= int(text) <= today_eat().year + 1:
            return "Not a plausible year."
        return None
    return None


def validate_field(kind: str, entry: dict, page_count: int | None) -> tuple[str, str | None]:
    """(validation, reason) for one returned field envelope."""
    reasons = []
    page = entry.get("source_page")
    if page_count and isinstance(page, int) and page > page_count:
        reasons.append(f"Source page {page} is beyond the document's {page_count} page(s).")
    value = entry.get("value")
    if value is None or not str(value).strip():
        return ("failed", " ".join(reasons)) if reasons else ("empty", None)
    reason = check(kind, str(value))
    if reason:
        reasons.append(reason)
    return ("failed", " ".join(reasons)) if reasons else ("passed", None)
