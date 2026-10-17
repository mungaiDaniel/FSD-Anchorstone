"""
General-ledger change requests.

    gl.account.create    open a GL account             one approver (gl.chart.approve)
    gl.account.change    rename, recode, regroup, flag, deactivate or reactivate

    gl.period.close      close a month                  one approver (gl.period.close.approve)
    gl.period.reopen     reopen the latest closed month two approvers (gl.period.reopen.approve), reason

Codes can change freely: journals reference the account id.
"""
from app.Approvals.handlers import Handler, register
from app.database.database import db
from app.Ledger import accounts, periods
from app.Ledger.model import PERIOD_CLOSED, PERIOD_OPEN, GlAccount, GlPeriod
from app.utils.audit_log import create_audit_log
from app.utils.dates import today_eat, utcnow
from app.utils.http import ValidationError


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


def _period_state(start) -> str:
    period = periods.find(start)
    return f"{period.status}:{period.reopen_count}" if period else "none"


@register
class PeriodClose(Handler):
    """payload = {period: "2026-09"}. Months close in order, and only once they have ended."""
    request_type = "gl.period.close"
    entity_type = "gl_period"
    submit_permission = "gl.period.close"

    def validate(self, payload):
        start = periods.parse_label(payload.get("period"))
        end = periods.bounds(start)[1]
        if end >= today_eat():
            raise ValidationError(f"{start:%Y-%m} hasn't ended yet; a period closes after its last day.")
        period = periods.find(start)
        if period is not None and period.status == PERIOD_CLOSED:
            raise ValidationError(f"GL period {period.label} is already closed.")
        earlier = (GlPeriod.query.filter(GlPeriod.period_start < start, GlPeriod.status == PERIOD_OPEN)
                   .order_by(GlPeriod.period_start).first())
        if earlier is not None:
            raise ValidationError(f"Close {earlier.label} first; periods close in order.")
        return {"period": f"{start:%Y-%m}"}

    def entity_id(self, payload):
        return payload["period"]

    def base_version(self, payload):
        return _period_state(periods.parse_label(payload["period"]))

    def describe(self, payload):
        return f"Close GL period {payload['period']}"

    def apply(self, request, actor):
        start = periods.parse_label(request.payload["period"])
        period = periods.ensure_period(start, request.maker_email)
        period = db.session.query(GlPeriod).filter(GlPeriod.id == period.id).with_for_update().populate_existing().one()
        period.status, period.closed_by, period.closed_at = PERIOD_CLOSED, actor.email, utcnow()
        period.last_change_request_id = request.id
        db.session.flush()
        create_audit_log("CLOSE_GL_PERIOD", target_type="gl_period", target_id=period.id, target_name=period.label,
                         description=f"GL period {period.label} closed (requested by {request.maker_email}).",
                         old_value={"status": PERIOD_OPEN}, new_value={"status": PERIOD_CLOSED})
        return {"gl_period_id": period.id}


@register
class PeriodReopen(Handler):
    """payload = {period: "2026-09", reason}. Only the latest closed period; two approvers (policy)."""
    request_type = "gl.period.reopen"
    entity_type = "gl_period"
    submit_permission = "gl.period.reopen"

    def validate(self, payload):
        start = periods.parse_label(payload.get("period"))
        reason = payload.get("reason")
        reason = reason.strip() if isinstance(reason, str) else ""
        if len(reason) < 10:
            raise ValidationError("Give the reason for reopening (at least 10 characters).")
        period = periods.find(start)
        if period is None or period.status != PERIOD_CLOSED:
            raise ValidationError(f"GL period {start:%Y-%m} isn't closed.")
        latest = periods.latest_closed()
        if latest.id != period.id:
            raise ValidationError(f"Only the latest closed period ({latest.label}) can be reopened.")
        return {"period": period.label, "reason": reason}

    def entity_id(self, payload):
        return payload["period"]

    def base_version(self, payload):
        return _period_state(periods.parse_label(payload["period"]))

    def describe(self, payload):
        return f"Reopen GL period {payload['period']}: {payload['reason']}"

    def apply(self, request, actor):
        period = (db.session.query(GlPeriod).filter(GlPeriod.period_start == periods.parse_label(request.payload["period"]))
                  .with_for_update().populate_existing().one())
        old = {"status": period.status, "closed_by": period.closed_by}
        period.status, period.closed_by, period.closed_at = PERIOD_OPEN, None, None
        period.reopen_count += 1
        period.last_change_request_id = request.id
        db.session.flush()
        create_audit_log("REOPEN_GL_PERIOD", target_type="gl_period", target_id=period.id, target_name=period.label,
                         description=f"GL period {period.label} reopened: {request.payload['reason']}",
                         old_value=old, new_value={"status": PERIOD_OPEN, "reason": request.payload["reason"],
                                                   "reopen_count": period.reopen_count})
        return {"gl_period_id": period.id, "reopen_count": period.reopen_count}
