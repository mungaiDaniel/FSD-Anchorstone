"""
Pre-selection (AI-08, AI-09, AI-11; 05 §6.2, §7).

    gather(application)            every metric the rules may use, computed in Python from
                                   CONFIRMED data only (approved reviews, the confirmed CRB
                                   status, the client record), each with its sources, or
                                   "missing" with the reason
    evaluate(rule_set, inputs)     a PURE function: the same inputs and rule set always give
                                   the same outcome and rule results (tested)
    screen(application_id, actor)  gather + evaluate with the rule-set version in force, and
                                   store the run (insert-only)
    decide(application_id, …)      a person records proceed / decline / more info with a
                                   reason. Proceeding against "Not qualified" is an override
                                   that a second person approves (credit.override). The
                                   system never declines on its own.

Outcome: any failed rule whose outcome is not_qualified → Not qualified; otherwise any
failed rule, or any applicable rule with missing data → Needs review; otherwise
Shortlisted. A rule that doesn't apply (party type, product) is "not applicable" and
doesn't count.
"""
import calendar
import hashlib
import json
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.Applications import checks as cross_checks
from app.Applications import review as reviews
from app.Applications import service as applications
from app.Applications.model import (
    DECISIONS,
    OUTCOME_LABELS,
    CreditDecision,
    LoanApplication,
    ScreeningRuleResult,
    ScreeningRun,
)
from app.Approvals import service as approvals
from app.Approvals.handlers import Handler, register
from app.Approvals.model import CR_OPEN, ChangeRequest
from app.database.database import db
from app.DocAI import metrics as statement_metrics
from app.DocAI.validators import parse_iso_date, parse_money
from app.Parties.model import Party, PartyOrganisation, PartyPerson
from app.Settings import business
from app.utils.audit_log import create_audit_log
from app.utils.dates import today_eat, utcnow
from app.utils.http import Conflict, ValidationError
from app.utils.money import round_money

WINDOW_MONTHS = 6
STATEMENT_TYPES = ("bank_statement", "mpesa_statement")
RATIO = Decimal("0.0001")


# ── Inputs: metrics from confirmed data ──


def _have(value, sources=(), **extra) -> dict:
    return {"value": value, "missing": None, "sources": list(sources), **extra}


def _missing(reason: str, sources=()) -> dict:
    return {"value": None, "missing": reason, "sources": list(sources)}


def _months_between(start: date, end: date) -> int:
    months = (end.year - start.year) * 12 + (end.month - start.month)
    return months - (1 if end.day < start.day else 0)


def _add_months(day: date, months: int) -> date:
    y, m = divmod(day.month - 1 + months, 12)
    year, month = day.year + y, m + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def _src(s: cross_checks.Source, path: str | None = None) -> dict:
    return {"type": s.doc_type, "extraction_id": s.extraction.id, "field": path,
            "page": s.pages.get(path) if path else None}


def _statements(app: LoanApplication, sources) -> dict:
    """The 6-month window metrics from the applicant's approved, reliable statements."""
    rows, covered, ends, used, unreliable = [], set(), [], [], 0
    for s in sources:
        if s.doc_type not in STATEMENT_TYPES or s.extraction.party_id != app.party_id:
            continue
        review = reviews.approved_review_for(s.extraction)
        if review.statement_unreliable:
            unreliable += 1
            continue
        mine = reviews.reviewed_rows(s.extraction, review)
        dates = [r.txn_date for r in mine if r.txn_date]
        start = parse_iso_date(s.values.get("header.period_from")) or (min(dates) if dates else None)
        end = parse_iso_date(s.values.get("header.period_to")) or (max(dates) if dates else None)
        if start is None or end is None:
            continue
        covered |= set(statement_metrics.months_between(start, end))
        ends.append(end)
        rows += mine
        used.append({"type": s.doc_type, "extraction_id": s.extraction.id, "review_id": review.id,
                     "period_from": start.isoformat(), "period_to": end.isoformat()})
    if not used:
        why = "the only statement(s) were marked not reliable" if unreliable else "no approved bank or M-Pesa statement"
        return {k: _missing(why) for k in ("avg_monthly_inflow_6m", "returned_items_6m", "lender_repayment_share_6m")}
    last = max(ends)
    window = statement_metrics.months_between(_add_months(last.replace(day=1), -(WINDOW_MONTHS - 1)), last)
    have = [m for m in window if m in covered]
    if len(have) < WINDOW_MONTHS:
        why = f"approved statements cover {len(have)} of the last {WINDOW_MONTHS} months"
        return {k: _missing(why, used) for k in ("avg_monthly_inflow_6m", "returned_items_6m",
                                                 "lender_repayment_share_6m")}
    in_window = [r for r in rows if r.txn_date and (r.txn_date.year, r.txn_date.month) in set(window)]
    credits = [r for r in in_window if r.credit and r.credit > 0]
    inflow = sum((r.credit for r in credits), Decimal("0"))
    returned = [r for r in in_window if statement_metrics.matches(
        r.description, business.get("ai.statements.returned_item_keywords"))]
    lenders = [r for r in in_window if r.debit and r.debit > 0 and statement_metrics.matches(
        r.description, business.get("ai.statements.lender_keywords"))]
    lender_total = sum((r.debit for r in lenders), Decimal("0"))
    window_text = f"{window[0][0]}-{window[0][1]:02d} to {window[-1][0]}-{window[-1][1]:02d}"
    out = {"avg_monthly_inflow_6m": _have(str(round_money(inflow / WINDOW_MONTHS)), used, window=window_text,
                                          transaction_ids=[r.id for r in credits]),
           "returned_items_6m": _have(len(returned), used, window=window_text,
                                      transaction_ids=[r.id for r in returned])}
    if inflow > 0:
        out["lender_repayment_share_6m"] = _have(str((lender_total / inflow).quantize(RATIO, rounding=ROUND_HALF_UP)),
                                                 used, window=window_text, transaction_ids=[r.id for r in lenders])
    else:
        out["lender_repayment_share_6m"] = _missing("no inflows in the last 6 months", used)
    return out


def gather(app: LoanApplication) -> dict:
    as_of = today_eat()
    party = db.session.get(Party, app.party_id)
    sources = cross_checks.confirmed_sources(app.id)
    check_results = cross_checks.run(app.id)
    by_check = {c["check"]: c for c in check_results}
    m: dict[str, dict] = {}

    start, origin = None, None
    if party.party_type == "organisation":
        org = db.session.get(PartyOrganisation, party.id)
        if org and org.registration_date:
            start, origin = org.registration_date, "registration date on the client record"
    if start is None and app.business_start_date:
        start, origin = app.business_start_date, "business start date on the application"
    m["months_in_business"] = _have(_months_between(start, as_of), [{"type": origin, "value": start.isoformat()}]) \
        if start else _missing("no registration date or business start date")

    m.update(_statements(app, sources))

    crb = applications.confirmed_crb(app.id)
    m["crb_status"] = _have(crb.status, [{"type": "crb_status", "id": crb.id, "bureau": crb.bureau,
                                          "date": crb.status_date.isoformat(), "confirmed_by": crb.confirmed_by}]) \
        if crb else _missing("no confirmed CRB status")

    valuations = [s for s in sources if s.doc_type == "valuation_report"]
    fsv = parse_money(valuations[0].values.get("forced_sale_value")) if valuations else None
    if fsv is not None:
        cover = (fsv / app.amount_requested * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        m["forced_sale_cover_percent"] = _have(str(cover), [_src(valuations[0], "forced_sale_value")],
                                               forced_sale_value=str(fsv))
    else:
        m["forced_sale_cover_percent"] = _missing("no approved valuation report with a forced-sale value")

    person = db.session.get(PartyPerson, party.id) if party.party_type == "person" else None
    if person and person.date_of_birth:
        maturity = _add_months(as_of, app.term_months)
        age = maturity.year - person.date_of_birth.year - (
            (maturity.month, maturity.day) < (person.date_of_birth.month, person.date_of_birth.day))
        m["age_at_maturity"] = _have(age, [{"type": "date of birth on the client record",
                                            "maturity": maturity.isoformat()}])
    else:
        m["age_at_maturity"] = _missing("no date of birth on the client record")

    identity = [by_check["name_consistent"], by_check["id_number_consistent"]]
    worst = cross_checks._worst([c["status"] for c in identity])
    m["identity_consistent"] = _missing("; ".join(c["reason"] for c in identity if c["status"] == "missing")) \
        if worst == "missing" else _have(worst, [{"type": "check", "check": c["check"]} for c in identity])
    for name in ("cr12_directors_match", "collateral_owner_match"):
        c = by_check[name]
        m[name] = _missing(c["reason"]) if c["status"] == "missing" else \
            _have(c["status"], [{"type": "check", "check": name}])

    m["amount_requested"] = _have(str(app.amount_requested))
    m["estimated_instalment"] = _have(str(app.estimated_instalment), note="ESTIMATE (phase 5 replaces it)")
    m["term_months"] = _have(app.term_months)
    return {"as_of": as_of.isoformat(),
            "application": {"id": app.id, "application_no": app.application_no, "party_type": party.party_type,
                            "product_code": app.product_code},
            "metrics": {k: m[k] for k in sorted(m)}, "checks": check_results}


def inputs_hash(inputs: dict) -> str:
    return hashlib.sha256(json.dumps(inputs, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


# ── Evaluation: a pure function of (rule set, inputs) ──


def _show(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, str):
        try:
            return f"{Decimal(value):,.2f}" if "." in value else value
        except ArithmeticError:
            return value
    return str(value)


def _compare(comparison: str, value, threshold) -> bool:
    if comparison == "between":
        return Decimal(str(threshold[0])) <= Decimal(str(value)) <= Decimal(str(threshold[1]))
    if comparison in ("in", "not_in"):
        hit = str(value) in [str(t) for t in threshold]
        return hit if comparison == "in" else not hit
    try:
        a, b = Decimal(str(value)), Decimal(str(threshold))
    except ArithmeticError:
        a, b = str(value), str(threshold)
    return {">=": a >= b, ">": a > b, "<=": a <= b, "<": a < b, "==": a == b, "!=": a != b}[comparison]


def _not_applicable(rule: dict, application: dict) -> str | None:
    applies = rule.get("applies_to") or {}
    if "party_types" in applies and application["party_type"] not in applies["party_types"]:
        return f"Applies to {', '.join(t + 's' for t in applies['party_types'])} only."
    if "products" in applies and application["product_code"] not in applies["products"]:
        return f"Applies to {', '.join(p.replace('_', ' ') + 's' for p in applies['products'])} only."
    return None


def evaluate(rule_set: dict, inputs: dict) -> tuple[str, list[dict]]:
    results = []
    for position, rule in enumerate(rule_set["rules"], 1):
        base = {"position": position, "rule_id": rule["id"], "description": rule["description"],
                "metric": rule["metric"], "comparison": rule["comparison"], "threshold": rule["threshold"],
                "value": None, "outcome_if_failed": None}
        na = _not_applicable(rule, inputs["application"])
        if na:
            results.append({**base, "result": "not_applicable", "reason": na})
            continue
        metric = inputs["metrics"].get(rule["metric"]) or {"value": None, "missing": "not computed"}
        threshold = rule["threshold"]
        if isinstance(threshold, dict):
            other = inputs["metrics"].get(threshold["of"]) or {"value": None, "missing": "not computed"}
            if other["value"] is None:
                results.append({**base, "result": "missing",
                                "reason": f"Missing data: {threshold['of'].replace('_', ' ')}: {other['missing']}."})
                continue
            threshold = str(Decimal(str(threshold["times"])) * Decimal(str(other["value"])))
            base["threshold"] = {**rule["threshold"], "value": threshold}
        if metric["value"] is None:
            results.append({**base, "result": "missing", "reason": f"Missing data: {metric['missing']}."})
            continue
        value = metric["value"]
        base["value"] = value
        shown = threshold if not isinstance(threshold, list) else f"{threshold[0]} and {threshold[1]}"
        if _compare(rule["comparison"], value, threshold):
            results.append({**base, "result": "pass", "reason": f"{rule['description']}: {_show(value)} "
                                                                 f"{rule['comparison']} {_show(shown)}."})
            continue
        outcome = rule["outcome_if_failed"]
        if isinstance(outcome, dict):
            outcome = outcome.get(str(value), outcome.get("*", "needs_review"))
        results.append({**base, "result": "fail", "outcome_if_failed": outcome,
                        "reason": f"{rule['description']}: {_show(value)} is not {rule['comparison']} {_show(shown)} "
                                  f"→ {OUTCOME_LABELS[outcome]}."})
    if any(r["result"] == "fail" and r["outcome_if_failed"] == "not_qualified" for r in results):
        return "not_qualified", results
    if any(r["result"] in ("fail", "missing") for r in results):
        return "needs_review", results
    return "shortlisted", results


# ── Runs ──


def current_rule_set():
    row = business.current_version("screening.rule_set")
    if row is None:
        raise Conflict("No pre-selection rule set is in force.")
    return row


def screen(application_id: int, actor) -> ScreeningRun:
    app = applications.lock(application_id)
    applications.assert_open(app)
    version = current_rule_set()
    inputs = gather(app)
    outcome, results = evaluate(version.value, inputs)
    run = ScreeningRun(application_id=app.id, rule_set_version_id=version.id, rule_set_version_no=version.version_no,
                       rule_set=version.value, inputs=inputs, inputs_sha256=inputs_hash(inputs), outcome=outcome,
                       evaluated_by=actor.email, evaluated_at=utcnow())
    db.session.add(run)
    db.session.flush()
    for r in results:
        db.session.add(ScreeningRuleResult(run_id=run.id, **r))
    create_audit_log("SCREEN_APPLICATION", target_type="loan_application", target_id=app.id,
                     target_name=app.application_no,
                     description=f"{OUTCOME_LABELS[outcome]} (rule set v{version.version_no})",
                     new_value={"run_id": run.id, "outcome": outcome, "rule_set_version_id": version.id,
                                "inputs_sha256": run.inputs_sha256})
    db.session.commit()
    return run


def latest_run(application_id: int) -> ScreeningRun | None:
    return (ScreeningRun.query.filter_by(application_id=application_id)
            .order_by(ScreeningRun.evaluated_at.desc(), ScreeningRun.id.desc()).first())


def run_dict(run: ScreeningRun) -> dict:
    rules = ScreeningRuleResult.query.filter_by(run_id=run.id).order_by(ScreeningRuleResult.position).all()
    return {"id": run.id, "application_id": run.application_id, "outcome": run.outcome,
            "outcome_label": OUTCOME_LABELS[run.outcome], "recommendation_only": True,
            "rule_set_version_id": run.rule_set_version_id, "rule_set_version_no": run.rule_set_version_no,
            "inputs": run.inputs, "inputs_sha256": run.inputs_sha256, "evaluated_by": run.evaluated_by,
            "evaluated_at": run.evaluated_at.isoformat(), "rules": [r.to_dict() for r in rules]}


# ── Decisions (AI-09): people decide ──


def _open_override(application_id: int) -> ChangeRequest | None:
    return (ChangeRequest.query.filter(ChangeRequest.request_type == "credit.override",
                                       ChangeRequest.entity_id == str(application_id),
                                       ChangeRequest.status.in_(CR_OPEN)).first())


def decide(application_id: int, data: dict, actor) -> dict:
    app = applications.lock(application_id)
    applications.assert_open(app)
    decision = str(data.get("decision") or "").strip()
    if decision not in DECISIONS:
        raise ValidationError(f"decision must be one of: {', '.join(DECISIONS)}.")
    reason = " ".join(str(data.get("reason") or "").split())
    if not reason:
        raise ValidationError("A reason is required for every decision.")
    run = latest_run(app.id)
    if run is None:
        raise ValidationError("Run the pre-selection first: a decision is recorded against its result.")
    if _open_override(app.id):
        raise Conflict("An override for this application is waiting for approval.")
    if decision == "proceed" and run.outcome == "not_qualified":
        cr = approvals.submit("credit.override", {"application_id": app.id, "run_id": run.id, "reason": reason},
                              actor, reason)
        return {"status": "pending_approval", "change_request_id": cr.id}
    row = _record(app, run, decision, reason, actor.email)
    db.session.commit()
    return {"status": "recorded", "decision": row.to_dict()}


def _record(app: LoanApplication, run: ScreeningRun, decision: str, reason: str, decided_by: str, *,
            override: bool = False, approved_by: str | None = None, change_request_id: int | None = None):
    row = CreditDecision(application_id=app.id, run_id=run.id, decision=decision, reason=reason, override=override,
                         decided_by=decided_by, decided_at=utcnow(), approved_by=approved_by,
                         change_request_id=change_request_id)
    db.session.add(row)
    if decision in ("proceed", "decline"):
        app.status = "decided"
    db.session.flush()
    create_audit_log("RECORD_CREDIT_DECISION", target_type="loan_application", target_id=app.id,
                     target_name=app.application_no,
                     description=f"{row.to_dict()['decision_label']} ({OUTCOME_LABELS[run.outcome]} "
                                 f"recommended{', override approved by ' + approved_by if override else ''}): {reason}",
                     new_value=row.to_dict())
    return row


@register
class CreditOverride(Handler):
    """Proceed to credit analysis although the rules recommended Not qualified (05 §7.4)."""
    request_type = "credit.override"
    entity_type = "loan_application"
    submit_permission = "credit.decide"

    def validate(self, payload):
        app = db.session.get(LoanApplication, payload.get("application_id")) \
            if isinstance(payload.get("application_id"), int) else None
        if app is None:
            raise ValidationError("application_id must be an application.")
        if app.status != "open":
            raise Conflict("A decision has already been recorded on this application.")
        run = latest_run(app.id)
        if run is None or run.id != payload.get("run_id") or run.outcome != "not_qualified":
            raise Conflict("The application was screened again since this override was requested.")
        reason = " ".join(str(payload.get("reason") or "").split())
        if not reason:
            raise ValidationError("A reason is required.")
        return {"application_id": app.id, "run_id": run.id, "reason": reason}

    def entity_id(self, payload):
        return str(payload["application_id"])

    def branch_id(self, payload):
        app = db.session.get(LoanApplication, payload["application_id"])
        return app.branch_id if app else None

    def base_version(self, payload):
        run = latest_run(payload["application_id"])
        return str(run.id) if run else None

    def describe(self, payload):
        app = db.session.get(LoanApplication, payload["application_id"])
        return f"Proceed with {app.application_no} despite a Not qualified recommendation: {payload['reason']}"

    def apply(self, request, actor):
        app = applications.lock(request.payload["application_id"])
        run = db.session.get(ScreeningRun, request.payload["run_id"])
        row = _record(app, run, "proceed", request.payload["reason"], request.maker_email, override=True,
                      approved_by=actor.email, change_request_id=request.id)
        return row.to_dict()


def decisions(application_id: int) -> list[dict]:
    return [d.to_dict() for d in CreditDecision.query.filter_by(application_id=application_id)
            .order_by(CreditDecision.decided_at, CreditDecision.id)]


# ── The queue (shortlisted, ready for credit analysis) ──


def ready_for_credit_ids() -> list[int]:
    out = []
    for app in LoanApplication.query.order_by(LoanApplication.created_at.desc(), LoanApplication.id.desc()):
        last = CreditDecision.query.filter_by(application_id=app.id).order_by(CreditDecision.id.desc()).first()
        if last is not None and last.decision == "decline":
            continue
        if last is not None and last.decision == "proceed":
            out.append(app.id)
            continue
        run = latest_run(app.id)
        if app.status == "open" and run is not None and run.outcome == "shortlisted":
            out.append(app.id)
    return out


def screening_summary(application_id: int) -> dict:
    run = latest_run(application_id)
    override = _open_override(application_id)
    return {"latest_run": run_dict(run) if run else None, "decisions": decisions(application_id),
            "pending_override": override.id if override else None}

