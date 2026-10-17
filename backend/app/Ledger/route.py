"""
General ledger.

    GET  /api/v1/gl/accounts                 chart of accounts (?active=1 for active only)
    GET  /api/v1/gl/accounts/<id>
    GET  /api/v1/gl/periods                  newest first
    GET  /api/v1/gl/journals/<id>            an entry with its lines
    GET  /api/v1/gl/posting-rules            latest version per event type (?event_type= for history)
    GET  /api/v1/gl/posting-rules/<id>
    GET  /api/v1/gl/trial-balance            ?as_of (default today) ?branch_id
    GET  /api/v1/gl/accounts/<id>/balance    ?as_of ?branch_id (headers include sub-accounts)
    GET  /api/v1/gl/accounts/<id>/statement  ?from ?to ?branch_id: opening, lines, running balance

Changes are change requests submitted through POST /api/v1/change-requests
(gl.account.create, gl.account.change, gl.period.close, gl.period.reopen,
gl.posting_rule.change).
"""
from flask import Blueprint, request

from app.auth import requires
from app.Ledger import accounts, balances, journals, periods, rules
from app.utils.dates import parse_date, today_eat
from app.utils.http import ValidationError, ok
from app.utils.money import as_str

ledger_v1 = Blueprint("ledger_v1", __name__)


@ledger_v1.get("/api/v1/gl/accounts")
@requires("gl.view")
def list_gl_accounts():
    only_active = request.args.get("active") in ("1", "true")
    return ok([a.to_dict() for a in accounts.list_accounts(include_inactive=not only_active)])


@ledger_v1.get("/api/v1/gl/accounts/<int:account_id>")
@requires("gl.view")
def get_gl_account(account_id):
    return ok(accounts.get_account(account_id).to_dict())


@ledger_v1.get("/api/v1/gl/periods")
@requires("gl.view")
def list_gl_periods():
    return ok([p.to_dict() for p in periods.list_periods()])


@ledger_v1.get("/api/v1/gl/journals/<int:entry_id>")
@requires("gl.view")
def get_journal(entry_id):
    entry = journals.get_entry(entry_id)
    out = entry.to_dict()
    reversal = journals.reversal_of(entry)
    out["reversed_by"] = reversal.journal_no if reversal else None
    return ok(out)


@ledger_v1.get("/api/v1/gl/posting-rules")
@requires("gl.view")
def list_posting_rules():
    """Latest version of each event type; ?event_type=X for that type's full history."""
    event_type = request.args.get("event_type")
    found = rules.history(event_type) if event_type else rules.current_rules()
    return ok([r.to_dict() for r in found])


@ledger_v1.get("/api/v1/gl/posting-rules/<int:rule_id>")
@requires("gl.view")
def get_posting_rule(rule_id):
    return ok(rules.get_rule(rule_id).to_dict())


def _branch_arg():
    value = request.args.get("branch_id")
    if value in (None, ""):
        return None
    if not value.isdigit():
        raise ValidationError("branch_id must be a number.")
    return int(value)


@ledger_v1.get("/api/v1/gl/trial-balance")
@requires("gl.view")
def get_trial_balance():
    as_of = parse_date(request.args.get("as_of"), "as_of", required=False) or today_eat()
    return ok(balances.trial_balance(as_of, _branch_arg()))


@ledger_v1.get("/api/v1/gl/accounts/<int:account_id>/balance")
@requires("gl.view")
def get_gl_account_balance(account_id):
    as_of = parse_date(request.args.get("as_of"), "as_of", required=False) or today_eat()
    branch_id = _branch_arg()
    return ok({"gl_account_id": account_id, "as_of": as_of.isoformat(), "branch_id": branch_id,
               "balance": as_str(balances.account_balance(account_id, as_of, branch_id))})


@ledger_v1.get("/api/v1/gl/accounts/<int:account_id>/statement")
@requires("gl.view")
def get_gl_account_statement(account_id):
    date_to = parse_date(request.args.get("to"), "to", required=False) or today_eat()
    date_from = parse_date(request.args.get("from"), "from", required=False) or date_to.replace(day=1)
    if date_from > date_to:
        raise ValidationError("from must be on or before to.")
    return ok(balances.account_statement(account_id, date_from, date_to, _branch_arg()))
