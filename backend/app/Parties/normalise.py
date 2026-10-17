"""
Normalising identifiers and contacts so duplicates are found whatever the
formatting ("12 345 678" and "12345678" are the same ID; "0712 345 678" and
"+254712345678" the same phone).

The investor migration (parties_from_investors) carries a frozen copy of these
rules; change both together or the migrated values won't match new captures.
"""
import re
import unicodedata

ID_TYPES = ("national_id", "passport", "alien_id", "kra_pin", "company_reg_no")
ID_TYPE_LABELS = {
    "national_id": "ID number",
    "passport": "Passport number",
    "alien_id": "Alien ID number",
    "kra_pin": "KRA PIN",
    "company_reg_no": "Company registration number",
}

_ID_SEPARATORS = re.compile(r"[\s\-/.]+")
_NOT_ALNUM = re.compile(r"[^A-Z0-9]")


def normalise_identifier(id_type: str, value: str | None) -> str | None:
    """Upper case without spaces, dashes, slashes or dots. A KRA PIN keeps letters and digits only."""
    if value is None:
        return None
    text = str(value).strip().upper()
    text = _NOT_ALNUM.sub("", text) if id_type == "kra_pin" else _ID_SEPARATORS.sub("", text)
    return text or None


def normalise_email(value: str | None) -> str | None:
    text = (value or "").strip().lower()
    return text or None


def normalise_phone(value: str | None) -> str | None:
    """Kenyan numbers to E.164 (+2547…, +2541…, landlines +25420…). None when it can't be read as one."""
    digits = re.sub(r"[\s\-().]", "", value or "")
    if not digits:
        return None
    if digits.startswith("+"):
        rest = digits[1:]
        return f"+{rest}" if rest.isdigit() and 8 <= len(rest) <= 15 else None
    if not digits.isdigit():
        return None
    if len(digits) == 10 and digits[0] == "0" and digits[1] != "0":  # mobile 07…/01…, landline 020…, 041…
        return f"+254{digits[1:]}"
    if len(digits) == 12 and digits.startswith("254") and digits[3] != "0":
        return f"+{digits}"
    if len(digits) == 9 and digits[0] in "71":
        return f"+254{digits}"
    return None


def normalise_name(value: str | None) -> str:
    """For name matching: accents folded ("Qaïda" = "Qaida"), upper case letters and digits, words
    sorted (so "Doe, Jane" = "Jane Doe"). Watchlist entries store the result (name_normalised), so a
    change here needs a migration that recomputes them (see fold_watchlist_name_accents)."""
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    words = re.sub(r"[^A-Z0-9 ]", " ", text.upper()).split()
    return " ".join(sorted(words))
