"""
Business-rule settings registry (08-working-assumptions.md §3).

The *shape* of every setting lives here in code: its type and validator, its
default (the working-assumption value), which scopes may override it, and when
a change takes effect. The *values* are rows in setting_versions, changed only
through maker-checker (app/Settings/handlers.py) and read with
app.Settings.business.get().

Adding a key is a code change plus a migration that seeds its version 1.
"""
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
    type: str                      # int / decimal / bool / enum / list / json
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


MIME_TYPES = ("application/pdf", "image/jpeg", "image/png", "image/heic", "image/tiff")

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
                      "changes save immediately and are audited.", wa_ref="WA-01", questionnaire_ref="B4"),
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
                      approvals_required=2, wa_ref="07 Q-CO2", questionnaire_ref="G1"),
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
