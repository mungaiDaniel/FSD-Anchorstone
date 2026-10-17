"""
General ledger.

    GET  /api/v1/gl/accounts                 chart of accounts (?active=1 for active only)
    GET  /api/v1/gl/accounts/<id>

Changes are change requests submitted through POST /api/v1/change-requests
(gl.account.create, gl.account.change).
"""
from flask import Blueprint, request

from app.auth import requires
from app.Ledger import accounts
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
