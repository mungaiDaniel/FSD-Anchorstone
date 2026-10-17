"""
General ledger.

    GET  /api/v1/gl/accounts                 chart of accounts (?active=1 for active only)
    GET  /api/v1/gl/accounts/<id>
    GET  /api/v1/gl/periods                  newest first
    GET  /api/v1/gl/journals/<id>            an entry with its lines
    GET  /api/v1/gl/posting-rules            latest version per event type (?event_type= for history)
    GET  /api/v1/gl/posting-rules/<id>

Changes are change requests submitted through POST /api/v1/change-requests
(gl.account.create, gl.account.change, gl.period.close, gl.period.reopen,
gl.posting_rule.change).
"""
from flask import Blueprint, request

from app.auth import requires
from app.Ledger import accounts, journals, periods, rules
from app.utils.http import ok

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
