"""
The document types the AI reads (FSD §15, 05 §2) and what is read from each.

This is the source the versioned files are built from:
    schemas/<type>.v<n>.json   JSON Schema sent with every call (structured output) and
                               re-checked in Python, by scripts/build_docai_schemas.py
    prompts/<type>.v<n>.md     the instructions, written by hand

A built schema file is never edited. Changing what a type reads means bumping its
SCHEMA_VERSION here and building a new file (the old one stays, so past extractions
still name a file that exists); tests/test_docai.py checks the files match this spec.

Each field has a kind, checked in Python after the model answers (validators.py):
    text, date, past_date, kenyan_id, kra_pin, sex, money, signed_money, integer, year
"""
from dataclasses import dataclass, field
from pathlib import Path

BASE = Path(__file__).parent
SCHEMA_DIR = BASE / "schemas"
PROMPT_DIR = BASE / "prompts"


@dataclass(frozen=True)
class F:
    name: str
    kind: str
    hint: str = ""


@dataclass(frozen=True)
class DocType:
    code: str
    label: str
    fields: tuple[F, ...]
    lists: dict[str, tuple[F, ...]] = field(default_factory=dict)  # repeating groups, e.g. CR12 directors
    statement: bool = False   # read page by page; transactions checked in Python (§6)
    schema_version: int = 1
    prompt_version: int = 1

    @property
    def schema_name(self) -> str:
        return f"{self.code}.v{self.schema_version}"

    @property
    def prompt_name(self) -> str:
        return f"{self.code}.v{self.prompt_version}"

    @property
    def schema_path(self) -> Path:
        return SCHEMA_DIR / f"{self.schema_name}.json"

    @property
    def prompt_path(self) -> Path:
        return PROMPT_DIR / f"{self.prompt_name}.md"

    def kinds(self) -> dict[str, str]:
        out = {f.name: f.kind for f in self.fields}
        for group, items in self.lists.items():
            out.update({f"{group}[].{f.name}": f.kind for f in items})
        return out


TYPES = (
    DocType("national_id", "National ID card", (
        F("id_number", "kenyan_id", "ID number, digits only"),
        F("full_name", "text", "Full name exactly as printed"),
        F("date_of_birth", "past_date"),
        F("sex", "sex", "M or F"),
        F("place_of_birth", "text"),
        F("date_of_issue", "past_date"),
        F("serial_number", "text", "Serial number of the card"),
        F("district", "text", "District of birth or issue, as printed"),
    )),
    DocType("passport", "Passport", (
        F("passport_number", "text"),
        F("surname", "text"),
        F("given_names", "text"),
        F("nationality", "text", "As printed, e.g. KENYAN or the 3-letter code"),
        F("date_of_birth", "past_date"),
        F("sex", "sex", "M or F"),
        F("date_of_issue", "past_date"),
        F("date_of_expiry", "date"),
        F("mrz_line_1", "text", "First machine-readable line, every character including <"),
        F("mrz_line_2", "text", "Second machine-readable line"),
    )),
    DocType("kra_pin", "KRA PIN certificate", (
        F("kra_pin", "kra_pin", "Personal Identification Number, e.g. A000000000Z"),
        F("taxpayer_name", "text"),
        F("taxpayer_type", "text", "Individual or non-individual, as printed"),
        F("registration_date", "past_date"),
        F("tax_obligations", "text", "The obligations listed, separated by semicolons"),
    )),
    DocType("cr12", "CR12 (company officials and shareholders)", (
        F("company_name", "text"),
        F("registration_number", "text"),
        F("cr12_date", "past_date", "Date the CR12 was issued"),
        F("registered_office", "text"),
        F("secretary", "text", "Company secretary's name, if listed"),
    ), lists={
        "directors": (F("name", "text"), F("id_or_passport_number", "text"), F("nationality", "text"),
                      F("shares", "integer", "Number of shares held, if shown")),
        "shareholders": (F("name", "text"), F("share_class", "text"), F("number_of_shares", "integer")),
    }),
    DocType("certificate_of_incorporation", "Certificate of incorporation / business registration", (
        F("entity_name", "text"),
        F("registration_number", "text"),
        F("registration_date", "past_date", "Date of incorporation or registration"),
        F("entity_type", "text", "e.g. private limited company, business name, partnership"),
    )),
    DocType("bank_statement", "Bank statement", (
        F("bank_name", "text"),
        F("branch", "text"),
        F("account_name", "text"),
        F("account_number_last4", "text", "Only the last 4 digits of the account number"),
        F("currency", "text", "3-letter code, e.g. KES"),
        F("period_from", "date", "Start of the statement period"),
        F("period_to", "date", "End of the statement period"),
    ), statement=True),
    DocType("mpesa_statement", "M-Pesa statement", (
        F("customer_name", "text"),
        F("mobile_number_last4", "text", "Only the last 4 digits of the phone number"),
        F("period_from", "date", "Start of the statement period"),
        F("period_to", "date", "End of the statement period"),
    ), statement=True),
    DocType("audited_financial_statements", "Audited financial statements", (
        F("entity_name", "text"),
        F("auditor", "text", "Audit firm"),
        F("year_end", "past_date", "Financial year end"),
        F("opinion_type", "text", "unqualified, qualified, adverse or disclaimer"),
        F("currency", "text"),
        F("units", "text", "How amounts are shown, e.g. KES or KES '000"),
        F("revenue", "signed_money"),
        F("cost_of_sales", "signed_money"),
        F("operating_profit", "signed_money"),
        F("finance_costs", "signed_money"),
        F("net_profit", "signed_money", "Profit after tax (negative for a loss)"),
        F("total_assets", "signed_money"),
        F("current_assets", "signed_money"),
        F("current_liabilities", "signed_money"),
        F("total_liabilities", "signed_money"),
        F("equity", "signed_money"),
        F("cash", "signed_money", "Cash and cash equivalents"),
    )),
    DocType("title_deed", "Title deed / certificate of lease", (
        F("title_number", "text"),
        F("registration_section", "text"),
        F("parcel_number", "text"),
        F("area", "text", "Area with its unit, as printed"),
        F("registered_proprietors", "text", "All registered owners, separated by semicolons"),
        F("tenure", "text", "freehold or leasehold"),
        F("lease_term", "text", "Term of a lease, if leasehold"),
        F("encumbrances", "text", "Charges, cautions or restrictions listed, separated by semicolons"),
        F("registration_date", "past_date"),
    )),
    DocType("logbook", "Logbook (vehicle registration certificate)", (
        F("registration_number", "text"),
        F("make", "text"),
        F("model", "text"),
        F("year_of_manufacture", "year"),
        F("chassis_number", "text"),
        F("engine_number", "text"),
        F("registered_owners", "text", "All registered owners, separated by semicolons"),
        F("financier_interest", "text", "Any financier or co-owner interest shown"),
        F("colour", "text"),
    )),
    DocType("valuation_report", "Valuation report", (
        F("valuer_firm", "text"),
        F("valuer_name", "text"),
        F("valuation_date", "past_date"),
        F("asset_identifier", "text", "Title number or vehicle registration number valued"),
        F("open_market_value", "money"),
        F("forced_sale_value", "money"),
        F("insurance_value", "money"),
        F("condition_notes", "text"),
        F("validity_period", "text", "How long the valuation is valid, as printed"),
    )),
    DocType("crb_report", "Credit reference bureau (CRB) report", (
        F("bureau_name", "text"),
        F("report_date", "past_date"),
        F("subject_name", "text"),
        F("subject_id_number", "text"),
        F("credit_score", "integer"),
        F("score_band", "text"),
        F("total_accounts", "integer"),
        F("open_accounts", "integer"),
        F("non_performing_accounts", "integer"),
        F("total_outstanding", "money"),
        F("total_in_arrears", "money"),
        F("defaults_listed", "text", "Lenders reporting defaults or listings, separated by semicolons"),
        F("enquiries_last_90_days", "integer"),
    )),
)
BY_CODE = {t.code: t for t in TYPES}
TYPE_CODES = tuple(BY_CODE)
DETECTABLE = TYPE_CODES + ("other",)  # what the model may say it sees


def get(code: str) -> DocType | None:
    return BY_CODE.get(code)


def label(code: str | None) -> str:
    if code == "other":
        return "a different kind of document"
    t = BY_CODE.get(code or "")
    return t.label if t else str(code)
