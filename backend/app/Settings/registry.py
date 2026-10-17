"""
Business-rule settings registry (08-working-assumptions.md §3).

The *shape* of every setting lives here in code: its type and validator, its
default (the working-assumption value), which scopes may override it, and when
a change takes effect. The *values* are rows in setting_versions, changed only
through maker-checker (app/Settings/handlers.py) and read with
app.Settings.business.get().

Adding a key is a code change plus a migration that seeds its version 1.
"""
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

from app.utils.http import ValidationError

# When a new value attaches to the work it governs.
IMMEDIATE = "immediate"            # the next action uses it
EVENT_DATE = "event_date"          # calculations use the value in force on the event's business date
AT_BOOKING = "at_booking"          # copied onto a record when it is created, never re-read
NEW_VERSIONS_ONLY = "new_versions_only"  # product defaults: only new product versions pick it up
BINDINGS = (IMMEDIATE, EVENT_DATE, AT_BOOKING, NEW_VERSIONS_ONLY)

SOURCES = ("working_assumption", "client_confirmed", "internal_decision")


@dataclass(frozen=True)
class SettingDefinition:
    key: str
    type: str                      # int / decimal / bool / enum / list / json / text
    default: Any                   # JSON-compatible (decimals as strings)
    validator: Callable[[Any], Any]
    binding: str
    category: str                  # security / investments / operations / lending / compliance / documents / ai
    description: str
    scopes: tuple[str, ...] = ("global",)
    approvals_required: int = 1
    in_use: bool = False           # read by code today (False = seeded for a later phase)
    wa_ref: str | None = None      # FSD working assumption or 07 question
    questionnaire_ref: str | None = None
    choices: tuple = field(default_factory=tuple)


# ── Validators: return the normalised JSON value or raise ValidationError ──


def int_between(lo: int, hi: int):
    def check(value):
        if isinstance(value, bool) or not isinstance(value, (int, str)):
            raise ValidationError(f"must be a whole number between {lo} and {hi}.")
        try:
            number = int(str(value).strip())
        except ValueError:
            raise ValidationError(f"must be a whole number between {lo} and {hi}.")
        if not lo <= number <= hi:
            raise ValidationError(f"must be between {lo} and {hi}.")
        return number
    return check


def percent(places: int = 4):
    def check(value):
        try:
            number = Decimal(str(value).strip())
        except (InvalidOperation, AttributeError):
            raise ValidationError("must be a percentage.")
        if not Decimal(0) <= number <= Decimal(100):
            raise ValidationError("must be between 0 and 100.")
        if number != number.quantize(Decimal(1).scaleb(-places)):
            raise ValidationError(f"must have at most {places} decimal places.")
        return f"{number:.{places}f}"
    return check


def boolean(value):
    if not isinstance(value, bool):
        raise ValidationError("must be true or false.")
    return value


def one_of(*choices):
    def check(value):
        if value not in choices:
            raise ValidationError(f"must be one of: {', '.join(choices)}.")
        return value
    return check


def label(max_len: int):
    """A short identifier such as a notice version (letters, digits, dot, dash, underscore)."""
    def check(value):
        text = str(value or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9._-]+", text) or len(text) > max_len:
            raise ValidationError(f"must be a label of up to {max_len} letters, digits, dots or dashes.")
        return text
    return check


def https_url(value):
    text = str(value or "").strip()
    if not re.fullmatch(r"https://[A-Za-z0-9.-]+(:\d+)?(/[^\s]*)?", text) or len(text) > 500:
        raise ValidationError("must be an https:// address of up to 500 characters.")
    return text


def int_list(lo: int, hi: int):
    def check(value):
        if not isinstance(value, list) or not value:
            raise ValidationError("must be a non-empty list of whole numbers.")
        numbers = [int_between(lo, hi)(v) for v in value]
        return sorted(set(numbers), reverse=True)
    return check


def subset_of(*choices):
    def check(value):
        if not isinstance(value, list) or any(v not in choices for v in value):
            raise ValidationError(f"must be a list drawn from: {', '.join(choices)}.")
        return sorted(set(value))
    return check


def ratio(places: int = 2):
    """A fraction from 0 to 1, e.g. a confidence threshold."""
    def check(value):
        try:
            number = Decimal(str(value).strip())
        except (InvalidOperation, AttributeError):
            raise ValidationError("must be a number from 0 to 1.")
        if not Decimal(0) <= number <= Decimal(1):
            raise ValidationError("must be between 0 and 1.")
        if number != number.quantize(Decimal(1).scaleb(-places)):
            raise ValidationError(f"must have at most {places} decimal places.")
        return f"{number:.{places}f}"
    return check


def keyword_list(max_items: int = 200, max_len: int = 60):
    """Words or phrases matched against statement descriptions (upper-cased, de-duplicated)."""
    def check(value):
        if not isinstance(value, list) or not value or len(value) > max_items:
            raise ValidationError(f"must be a list of 1 to {max_items} words or phrases.")
        out = set()
        for item in value:
            text = " ".join(str(item or "").split()).upper()
            if not text or len(text) > max_len:
                raise ValidationError(f"each entry must be 1 to {max_len} characters.")
            out.add(text)
        return sorted(out)
    return check


def price_table(value):
    """{model id: {"input": USD per million input tokens, "output": USD per million output tokens}}."""
    if not isinstance(value, dict) or not value:
        raise ValidationError("must map each model to its input and output price per million tokens.")
    out = {}
    for model, prices in value.items():
        label(80)(model)
        if not isinstance(prices, dict) or set(prices) != {"input", "output"}:
            raise ValidationError(f"{model} needs exactly an input and an output price.")
        row = {}
        for side in ("input", "output"):
            try:
                number = Decimal(str(prices[side]).strip())
            except (InvalidOperation, AttributeError):
                raise ValidationError(f"{model} {side} price must be a number.")
            if number < 0 or number != number.quantize(Decimal("0.0001")):
                raise ValidationError(f"{model} {side} price must be zero or more, with at most 4 decimal places.")
            row[side] = f"{number:.4f}"
        out[model] = row
    return out


AI_PRICES = {  # USD per million tokens, Anthropic list prices October 2026
    "claude-opus-5-5": {"input": "4.0000", "output": "20.0000"},
    "claude-sonnet-5-5": {"input": "2.0000", "output": "10.0000"},
    "claude-haiku-5-5": {"input": "0.1000", "output": "0.5000"},
}
LENDER_KEYWORDS = ("FULIZA", "M-SHWARI", "MSHWARI", "KCB M-PESA", "TALA", "BRANCH INTERNATIONAL", "ZENKA", "OKOLEA",
                   "HUSTLER FUND", "LOAN REPAYMENT")
RETURNED_ITEM_KEYWORDS = ("RTD", "UNPAID", "RETURNED", "INSUFF", "DISHON", "BOUNCED")

MIME_TYPES = ("application/pdf", "image/jpeg", "image/png", "image/heic", "image/tiff")
# Compulsory KYC details (07 Q-C1); the names are checked in app/Parties/service.py missing_fields().
PERSON_REQUIRED_FIELDS = ("name", "id_document", "kra_pin", "date_of_birth", "mobile", "physical_address",
                          "next_of_kin")
WATCHLISTS = ("internal_blacklist", "pep", "sanctions_un")  # app/Parties/model.py WATCHLISTS
UN_SANCTIONS_URL = "https://scsanctions.un.org/resources/xml/en/consolidated.xml"
ORGANISATION_REQUIRED_FIELDS = ("legal_name", "registration_no", "kra_pin", "registration_date",
                                "director_with_id", "phone", "physical_address")

DEFINITIONS = [
    # ── Security (FSD SEC-02, 07 Q-IT5). Two approvers for any change. ──
    SettingDefinition("security.password_min_length", "int", 10, int_between(8, 128), IMMEDIATE, "security",
                      "Minimum password length. The FSD asks for at least 8; 10 is kept so existing passwords "
                      "aren't weakened. Can't go below 8.", approvals_required=2, in_use=True,
                      wa_ref="FSD SEC-02", questionnaire_ref="I6"),
    SettingDefinition("security.login_max_failures", "int", 5, int_between(1, 100), IMMEDIATE, "security",
                      "Failed sign-ins for one email within the window before the account locks.",
                      approvals_required=2, in_use=True, wa_ref="FSD SEC-02", questionnaire_ref="I6"),
    SettingDefinition("security.login_window_minutes", "int", 15, int_between(1, 1440), IMMEDIATE, "security",
                      "Window for counting failed sign-ins (minutes).", approvals_required=2, in_use=True,
                      wa_ref="FSD SEC-02", questionnaire_ref="I6"),
    SettingDefinition("security.login_lock_minutes", "int", 15, int_between(1, 1440), IMMEDIATE, "security",
                      "How long a locked account stays locked (minutes).", approvals_required=2, in_use=True,
                      wa_ref="07 Q-IT5", questionnaire_ref="I6"),
    SettingDefinition("security.login_ip_max_failures", "int", 20, int_between(1, 10000), IMMEDIATE, "security",
                      "Failed sign-ins from one IP address within the window before it is refused.",
                      approvals_required=2, in_use=True, wa_ref="07 Q-IT5", questionnaire_ref="I6"),
    SettingDefinition("security.password_max_age_days", "int", 90, int_between(0, 3650), IMMEDIATE, "security",
                      "Days before a password must be changed (0 = never). Not enforced yet (phase 2b).",
                      approvals_required=2, wa_ref="FSD SEC-02", questionnaire_ref="I6"),
    SettingDefinition("security.password_history", "int", 0, int_between(0, 100), IMMEDIATE, "security",
                      "Previous passwords that can't be reused (0 = none of them). Not enforced yet (phase 2b).",
                      approvals_required=2, wa_ref="FSD SEC-02", questionnaire_ref="I6"),
    SettingDefinition("security.idle_timeout_minutes", "int", 30, int_between(5, 480), IMMEDIATE, "security",
                      "Sign out after this many idle minutes. Not enforced yet.", approvals_required=2,
                      wa_ref="07 Q-IT5", questionnaire_ref="I6"),
    # ── Investments ──
    SettingDefinition("investments.wht_rate_percent", "decimal", "0.0000", percent(4), EVENT_DATE, "investments",
                      "Withholding tax on investor interest (%), applied to a month by the value in force on its "
                      "last day. 0% and hidden until compliance confirms the treatment.", in_use=True,
                      wa_ref="WA-03", questionnaire_ref="B5"),
    # ── Operations ──
    SettingDefinition("email.max_attempts", "int", 3, int_between(1, 10), IMMEDIATE, "operations",
                      "Send attempts before a queued email is marked failed.", in_use=True, wa_ref="internal"),
    SettingDefinition("notifications.reminder_days_before", "list", [3, 0], int_list(0, 30), EVENT_DATE,
                      "operations", "Repayment reminders: days before the due date (0 = on the day).",
                      wa_ref="FSD NTF-01", questionnaire_ref="internal"),
    # ── Lending (not used until phase 5) ──
    SettingDefinition("lending.max_open_loans_per_client", "int", 3, int_between(1, 50), AT_BOOKING, "lending",
                      "Most open loans one client may hold.", wa_ref="WA-05", questionnaire_ref="C7"),
    SettingDefinition("lending.max_open_loans_per_group", "int", 3, int_between(1, 50), AT_BOOKING, "lending",
                      "Most open loans one related-party group may hold.", wa_ref="WA-05", questionnaire_ref="C7"),
    SettingDefinition("lending.in_duplum_enabled", "bool", True, boolean, IMMEDIATE, "lending",
                      "Stop accruing when unpaid interest and charges reach the outstanding principal.",
                      wa_ref="07 Q-CO4", questionnaire_ref="E5"),
    SettingDefinition("lending.penalty_grace_days", "int", 7, int_between(0, 90), NEW_VERSIONS_ONLY, "lending",
                      "Days past due before penalty interest starts (product default).", scopes=("global", "product"),
                      wa_ref="WA-06", questionnaire_ref="E4"),
    # ── Compliance ──
    SettingDefinition("kyc.maker_checker_fields", "list", ["bank", "identity", "payout"],
                      subset_of("identity", "bank", "payout", "email", "phone", "address"), IMMEDIATE, "compliance",
                      "Investor / party details whose changes need a second person's approval. Other contact "
                      "changes save immediately and are audited.", in_use=True, wa_ref="WA-01",
                      questionnaire_ref="B4"),
    SettingDefinition("kyc.required_fields.person", "list", sorted(PERSON_REQUIRED_FIELDS),
                      subset_of(*PERSON_REQUIRED_FIELDS), IMMEDIATE, "compliance",
                      "Details an individual must have before KYC can be verified.", in_use=True,
                      wa_ref="07 Q-C1", questionnaire_ref="C8"),
    SettingDefinition("kyc.required_fields.organisation", "list", sorted(ORGANISATION_REQUIRED_FIELDS),
                      subset_of(*ORGANISATION_REQUIRED_FIELDS), IMMEDIATE, "compliance",
                      "Details an organisation must have before KYC can be verified.", in_use=True,
                      wa_ref="07 Q-C1", questionnaire_ref="C9"),
    SettingDefinition("consent.notice_version", "text", "v1", label(30), IMMEDIATE, "compliance",
                      "Version of the privacy notice shown to clients; stored with every consent recorded.",
                      in_use=True, wa_ref="07 Q-CO1", questionnaire_ref="G3"),
    SettingDefinition("screening.lists_enabled", "list", ["internal_blacklist", "pep"],
                      subset_of(*WATCHLISTS), IMMEDIATE, "compliance",
                      "Watchlists every client is screened against at onboarding, on identity changes and daily. "
                      "Add sanctions_un once the UN list import is on and compliance has confirmed it.", in_use=True,
                      wa_ref="07 Q-CO6 / FSD KYC-06", questionnaire_ref="G6"),
    SettingDefinition("screening.un_sanctions.import_enabled", "bool", False, boolean, IMMEDIATE, "compliance",
                      "Download the UN Security Council consolidated sanctions list daily into the sanctions_un "
                      "watchlist. Off until compliance confirms the source and refresh.", in_use=True,
                      wa_ref="07 Q-CO6 / FSD KYC-06", questionnaire_ref="G6"),
    SettingDefinition("screening.un_sanctions.source_url", "text", UN_SANCTIONS_URL, https_url, IMMEDIATE,
                      "compliance", "Where the UN consolidated list XML is downloaded from. Two approvers: a wrong "
                      "source could delist sanctioned names.", approvals_required=2, in_use=True,
                      wa_ref="07 Q-CO6 / FSD KYC-06", questionnaire_ref="G6"),
    SettingDefinition("retention.documents_years_after_end", "int", 7, int_between(1, 30), EVENT_DATE, "compliance",
                      "Years documents are kept after the relationship ends (including declined applicants).",
                      wa_ref="WA-12", questionnaire_ref="G5"),
    SettingDefinition("retention.ai_raw_output_months", "int", 24, int_between(1, 120), EVENT_DATE, "compliance",
                      "Months raw AI extraction outputs are kept after the decision.", wa_ref="07 Q-CO8",
                      questionnaire_ref="G5"),
    SettingDefinition("retention.audit_years", "int", 7, int_between(1, 30), EVENT_DATE, "compliance",
                      "Years audit logs and screening runs are kept.", wa_ref="07 Q-CO8", questionnaire_ref="G5"),
    SettingDefinition("access.out_of_portfolio_mode", "enum", "flag", one_of("flag", "block"), IMMEDIATE,
                      "compliance", "Opening a record outside your portfolio: flag it (log and report) or block it.",
                      wa_ref="07 Q-CO3", questionnaire_ref="D4", choices=("flag", "block")),
    # ── Documents (used by the document store) ──
    SettingDefinition("documents.allowed_types", "list", sorted(MIME_TYPES), subset_of(*MIME_TYPES), IMMEDIATE,
                      "documents", "File types accepted for upload.", in_use=True, wa_ref="07 Q-IT9",
                      questionnaire_ref="I9"),
    SettingDefinition("documents.max_mb", "int", 25, int_between(1, 100), IMMEDIATE, "documents",
                      "Largest file accepted for upload (MB).", in_use=True, wa_ref="07 Q-IT9", questionnaire_ref="I9"),
    # ── AI ──
    SettingDefinition("ai.enabled", "bool", False, boolean, IMMEDIATE, "ai",
                      "AI document processing. Stays off until data location and the DPO are confirmed.",
                      approvals_required=2, in_use=True, wa_ref="07 Q-CO2", questionnaire_ref="G1"),
    SettingDefinition("ai.model_extract", "text", "claude-opus-5-5", label(80), IMMEDIATE, "ai",
                      "Claude model that reads documents. Copied onto each extraction when it is requested. A change "
                      "needs an accuracy run on the sample set first (05 §12).", approvals_required=2, in_use=True,
                      wa_ref="05 ADR-05-2", questionnaire_ref="H5"),
    SettingDefinition("ai.effort", "enum", "medium", one_of("low", "medium", "high"), IMMEDIATE, "ai",
                      "How much reasoning the model spends per page (higher reads harder scans, costs more).",
                      in_use=True, wa_ref="internal", questionnaire_ref="H6", choices=("low", "medium", "high")),
    SettingDefinition("ai.max_attempts", "int", 3, int_between(1, 5), IMMEDIATE, "ai",
                      "Tries per AI call when the service is busy or failing, with a growing pause between "
                      "them. Then the document is marked 'extraction failed' for a retry or manual capture.",
                      in_use=True, wa_ref="05 §11"),
    SettingDefinition("ai.price_table", "json", AI_PRICES, price_table, IMMEDIATE, "ai",
                      "Price per million input and output tokens (USD) for each model, used to estimate the cost "
                      "of every AI call.", in_use=True, wa_ref="05 §11", questionnaire_ref="H6"),
    SettingDefinition("ai.statements.lender_keywords", "list", sorted(LENDER_KEYWORDS), keyword_list(), IMMEDIATE,
                      "ai", "Statement descriptions containing any of these words count as repayments to other "
                      "lenders.", in_use=True, wa_ref="05 §6.2", questionnaire_ref="H3"),
    SettingDefinition("ai.review.confidence_threshold", "decimal", "0.85", ratio(2), IMMEDIATE, "ai",
                      "Values the AI read with less confidence than this are highlighted for the reviewer. Every "
                      "value still needs an explicit accept or correct.", in_use=True, wa_ref="07 Q-C8",
                      questionnaire_ref="H2"),
    SettingDefinition("ai.statements.returned_item_keywords", "list", sorted(RETURNED_ITEM_KEYWORDS), keyword_list(),
                      IMMEDIATE, "ai", "Statement descriptions containing any of these words count as bounced or "
                      "returned items.", in_use=True, wa_ref="05 §6.2", questionnaire_ref="H3"),
]

REGISTRY: dict[str, SettingDefinition] = {d.key: d for d in DEFINITIONS}
assert len(REGISTRY) == len(DEFINITIONS), "duplicate setting key"


def definition(key: str) -> SettingDefinition:
    d = REGISTRY.get(key)
    if d is None:
        raise ValidationError(f"Unknown setting: {key}.")
    return d


def normalise(key: str, value):
    d = definition(key)
    try:
        return d.validator(value)
    except ValidationError as e:
        raise ValidationError(f"{key} {e.message}")
