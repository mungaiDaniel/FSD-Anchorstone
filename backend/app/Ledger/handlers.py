"""
General-ledger change requests.

    gl.account.create    open a GL account             one approver (gl.chart.approve)
    gl.account.change    rename, recode, regroup, flag, deactivate or reactivate

Codes can change freely: journals reference the account id.
"""
from app.Approvals.handlers import Handler, register
from app.database.database import db
from app.Ledger import accounts
from app.Ledger.model import GlAccount


@register
class AccountCreate(Handler):
    request_type = "gl.account.create"
    entity_type = "gl_account"
    submit_permission = "gl.chart.edit"

    def validate(self, payload):
        return accounts.validate_new(payload)

    def entity_id(self, payload):
        return payload["code"]

    def describe(self, payload):
        return f"Open GL account {payload['code']} {payload['name']} ({payload['account_type']})"

    def apply(self, request, actor):
        account = GlAccount(**request.payload, is_active=True, version=1, created_by=request.maker_email)
        db.session.add(account)
        db.session.flush()
        return {"gl_account_id": account.id}


@register
class AccountChange(Handler):
    request_type = "gl.account.change"
    entity_type = "gl_account"
    submit_permission = "gl.chart.edit"

    def validate(self, payload):
        account = accounts.get_account(payload.get("gl_account_id"))
        diff = accounts.validate_change(account, payload.get("changes"))
        return {"gl_account_id": account.id, "changes": diff}

    def entity_id(self, payload):
        return str(payload["gl_account_id"])

    def base_version(self, payload):
        account = db.session.get(GlAccount, payload["gl_account_id"])
        return str(account.version) if account else "gone"

    def old_value(self, payload):
        account = db.session.get(GlAccount, payload["gl_account_id"])
        return {k: getattr(account, k) for k in payload["changes"]} if account else None

    def describe(self, payload):
        account = db.session.get(GlAccount, payload["gl_account_id"])
        name = f"{account.code} {account.name}" if account else f"#{payload['gl_account_id']}"
        fields = ", ".join(f"{k} → {v}" for k, v in payload["changes"].items())
        return f"Change GL account {name}: {fields}"

    def apply(self, request, actor):
        account = db.session.query(GlAccount).filter(GlAccount.id == request.payload["gl_account_id"]) \
            .with_for_update().one()
        for field, value in request.payload["changes"].items():
            setattr(account, field, value)
        account.version += 1
        account.updated_by = request.maker_email
        db.session.flush()
        return {"gl_account_id": account.id, "version": account.version}
