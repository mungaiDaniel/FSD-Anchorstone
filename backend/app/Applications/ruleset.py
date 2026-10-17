"""
The pre-selection rule set as data (AI-08; 05 §7.1). Stored as the setting
screening.rule_set; changing it is a settings.change request (maker-checker),
which makes a new immutable version. No code, no eval, no AI.

    {"rules": [{"id", "description", "metric", "comparison", "threshold",
                "outcome_if_failed", "applies_to"?}]}

    metric             a name from METRICS (computed in Python, screening.py)
    comparison         >=  >  <=  <  ==  !=  in  not_in  between
    threshold          a number, text, a list (in / not_in), [low, high] (between), or
                       {"times": 3, "of": "estimated_instalment"} (a multiple of another metric)
    outcome_if_failed  needs_review | not_qualified, or by value: {"listed": "not_qualified",
                       "*": "needs_review"}
    applies_to         {"party_types": [...], "products": [...]}: otherwise the rule is
                       recorded as not applicable and doesn't change the outcome

Fairness (AI-11): protected attributes (gender, marital status, religion, ethnicity,
health) can't be referenced; nor can any metric not in METRICS. Age is only available
as age_at_maturity, which WA-10 sets with the client (Q-CO10).

This module is pure (no database), so the settings registry can validate with it.
"""
from decimal import Decimal, InvalidOperation

from app.utils.http import ValidationError

COMPARISONS = (">=", ">", "<=", "<", "==", "!=", "in", "not_in", "between")
FAIL_OUTCOMES = ("needs_review", "not_qualified")
PARTY_TYPES = ("person", "organisation")
PRODUCT_CODES = ("business_loan", "bridge_loan", "asset_finance")
PROTECTED = {"gender": "gender", "marital_status": "marital status", "religion": "religion",
             "ethnicity": "ethnicity", "health": "health"}

# name → (kind, description). kind: number | text. Computed from confirmed data in screening.py.
METRICS = {
    "months_in_business": ("number", "Whole months since the business started (registration date, else the date "
                                     "entered on the application)"),
    "avg_monthly_inflow_6m": ("number", "Average monthly credits over the last 6 calendar months of approved "
                                        "statements (KES)"),
    "crb_status": ("text", "Confirmed CRB status: clear, listed or previously_listed_cleared"),
    "forced_sale_cover_percent": ("number", "Forced-sale value from the approved valuation ÷ amount requested × 100"),
    "age_at_maturity": ("number", "Applicant's age in whole years at the end of the term"),
    "identity_consistent": ("text", "Name and ID checks combined: pass, needs_review or fail"),
    "cr12_directors_match": ("text", "CR12 directors against captured directors: pass, needs_review or fail"),
    "collateral_owner_match": ("text", "Collateral owners against the applicant and guarantors"),
    "returned_items_6m": ("number", "Bounced / returned items in the last 6 months of approved statements"),
    "lender_repayment_share_6m": ("number", "Repayments to other lenders ÷ inflows, last 6 months (0 to 1)"),
    "amount_requested": ("number", "Amount requested (KES)"),
    "estimated_instalment": ("number", "ESTIMATED monthly instalment (KES)"),
    "term_months": ("number", "Term in months"),
}

DEFAULT_RULE_SET = {"rules": [
    {"id": "R1", "description": "Time in business at least 12 months", "metric": "months_in_business",
     "comparison": ">=", "threshold": 12, "outcome_if_failed": "not_qualified"},
    {"id": "R2", "description": "Average monthly inflows (6 months) at least 3 × instalment",
     "metric": "avg_monthly_inflow_6m", "comparison": ">=", "threshold": {"times": 3, "of": "estimated_instalment"},
     "outcome_if_failed": "needs_review"},
    {"id": "R3", "description": "CRB: listed → Not qualified; cleared → Needs review", "metric": "crb_status",
     "comparison": "==", "threshold": "clear",
     "outcome_if_failed": {"listed": "not_qualified", "previously_listed_cleared": "needs_review"}},
    {"id": "R4", "description": "Forced-sale cover at least 125%", "metric": "forced_sale_cover_percent",
     "comparison": ">=", "threshold": 125, "outcome_if_failed": "needs_review",
     "applies_to": {"products": ["asset_finance", "business_loan"]}},
    {"id": "R5", "description": "Age 18 to 70 at maturity", "metric": "age_at_maturity", "comparison": "between",
     "threshold": [18, 70], "outcome_if_failed": "not_qualified", "applies_to": {"party_types": ["person"]}},
    {"id": "R6", "description": "Name and ID consistent across documents", "metric": "identity_consistent",
     "comparison": "==", "threshold": "pass", "outcome_if_failed": "needs_review"},
    {"id": "R7", "description": "CR12 directors match the directors captured", "metric": "cr12_directors_match",
     "comparison": "==", "threshold": "pass", "outcome_if_failed": "needs_review",
     "applies_to": {"party_types": ["organisation"]}},
    {"id": "R8", "description": "Bounced items at most 2 in 6 months", "metric": "returned_items_6m",
     "comparison": "<=", "threshold": 2, "outcome_if_failed": "needs_review"},
    {"id": "R9", "description": "Other lenders' repayments below 50% of inflows", "metric": "lender_repayment_share_6m",
     "comparison": "<", "threshold": "0.50", "outcome_if_failed": "needs_review"},
]}


# Version 2 (migration d4e5f6a7b8ca): version 1 plus rule 10. DEFAULT_RULE_SET stays version 1, the seeded default.
RULE_10 = {"id": "R10", "description": "Collateral owner is the applicant or a guarantor",
           "metric": "collateral_owner_match", "comparison": "==", "threshold": "pass",
           "outcome_if_failed": "needs_review", "applies_to": {"products": ["asset_finance", "business_loan"]}}
RULE_SET_V2 = {"rules": DEFAULT_RULE_SET["rules"] + [RULE_10]}


def _number(value, where: str) -> str:
    if isinstance(value, bool):
        raise ValidationError(f"{where} must be a number.")
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, AttributeError):
        raise ValidationError(f"{where} must be a number.")
    if not number.is_finite():
        raise ValidationError(f"{where} must be a number.")
    return value if isinstance(value, int) else str(number)


def _metric(name, where: str) -> str:
    key = str(name or "").strip()
    if key in PROTECTED or any(p in key for p in PROTECTED):
        raise ValidationError(f"{where}: {PROTECTED.get(key, key)} is a protected attribute and can never be used "
                              "in pre-selection rules (AI-11).")
    if key not in METRICS:
        raise ValidationError(f"{where}: unknown metric '{key}'. Use one of: {', '.join(METRICS)}.")
    return key


def _threshold(rule: dict, where: str):
    comparison, value, kind = rule["comparison"], rule.get("threshold"), METRICS[rule["metric"]][0]
    if isinstance(value, dict):
        if set(value) != {"times", "of"} or comparison not in (">=", ">", "<=", "<"):
            raise ValidationError(f"{where}: a multiple threshold is {{\"times\": n, \"of\": metric}} with >, >=, < "
                                  "or <=.")
        other = _metric(value["of"], where)
        if METRICS[other][0] != "number" or kind != "number":
            raise ValidationError(f"{where}: a multiple compares two numeric metrics.")
        return {"times": _number(value["times"], f"{where} times"), "of": other}
    if comparison == "between":
        if not isinstance(value, list) or len(value) != 2:
            raise ValidationError(f"{where}: between needs [low, high].")
        low, high = (_number(v, f"{where} threshold") for v in value)
        if Decimal(str(low)) > Decimal(str(high)):
            raise ValidationError(f"{where}: low is above high.")
        return [low, high]
    if comparison in ("in", "not_in"):
        if not isinstance(value, list) or not value:
            raise ValidationError(f"{where}: {comparison} needs a list.")
        return [_number(v, f"{where} threshold") if kind == "number" else str(v) for v in value]
    if kind == "number":
        if comparison not in (">=", ">", "<=", "<", "==", "!="):
            raise ValidationError(f"{where}: {comparison} doesn't apply to a number.")
        return _number(value, f"{where} threshold")
    if comparison not in ("==", "!="):
        raise ValidationError(f"{where}: {rule['metric']} is text; use ==, !=, in or not_in.")
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{where}: threshold must be text.")
    return value.strip()


def _outcome(value, where: str):
    if isinstance(value, str):
        if value not in FAIL_OUTCOMES:
            raise ValidationError(f"{where}: outcome_if_failed must be needs_review or not_qualified (a rule can never "
                                  "approve).")
        return value
    if isinstance(value, dict) and value:
        return {str(k): _outcome(v, where) for k, v in value.items()}
    raise ValidationError(f"{where}: outcome_if_failed must be needs_review, not_qualified or a map of them.")


def _applies(value, where: str):
    if value in (None, {}):
        return None
    if not isinstance(value, dict) or not set(value) <= {"party_types", "products"}:
        raise ValidationError(f"{where}: applies_to takes party_types and/or products.")
    out = {}
    for key, allowed in (("party_types", PARTY_TYPES), ("products", PRODUCT_CODES)):
        if key in value:
            items = value[key]
            if not isinstance(items, list) or not items or any(i not in allowed for i in items):
                raise ValidationError(f"{where}: {key} must be a list drawn from {', '.join(allowed)}.")
            out[key] = sorted(set(items))
    return out


def validate(value) -> dict:
    """The normalised rule set, or ValidationError."""
    if not isinstance(value, dict) or not isinstance(value.get("rules"), list) or not value["rules"]:
        raise ValidationError('must be {"rules": [...]} with at least one rule.')
    out, seen = [], set()
    for i, rule in enumerate(value["rules"], 1):
        where = f"rule {i}"
        if not isinstance(rule, dict):
            raise ValidationError(f"{where} must be an object.")
        unknown = set(rule) - {"id", "description", "metric", "comparison", "threshold", "outcome_if_failed",
                               "applies_to"}
        if unknown:
            raise ValidationError(f"{where}: unknown field(s) {', '.join(sorted(unknown))}.")
        rule_id = str(rule.get("id") or "").strip()
        if not rule_id or len(rule_id) > 40 or rule_id in seen:
            raise ValidationError(f"{where}: id is required, at most 40 characters and unique.")
        seen.add(rule_id)
        where = f"rule {rule_id}"
        description = " ".join(str(rule.get("description") or "").split())
        if not description:
            raise ValidationError(f"{where}: description is required.")
        clean = {"id": rule_id, "description": description, "metric": _metric(rule.get("metric"), where),
                 "comparison": rule.get("comparison")}
        if clean["comparison"] not in COMPARISONS:
            raise ValidationError(f"{where}: comparison must be one of {', '.join(COMPARISONS)}.")
        clean["threshold"] = _threshold(clean | {"threshold": rule.get("threshold")}, where)
        clean["outcome_if_failed"] = _outcome(rule.get("outcome_if_failed"), where)
        applies = _applies(rule.get("applies_to"), where)
        if applies:
            clean["applies_to"] = applies
        out.append(clean)
    return {"rules": out}
