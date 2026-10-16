"""
Changing a business-rule setting is a change request:

    settings.change            one approver   (most keys)
    settings.change_security   two approvers  (keys with approvals_required = 2)

payload = {key, value, effective_from, scope_type, scope_id, source, evidence}

The new version can't be dated in the past (nothing is rewritten after the
fact), and an event-dated key can't take effect inside an approved interest
month. base_version is the version in force at submit, so two overlapping
changes to the same key can't both be approved blind.
"""
from datetime import date

from app.Approvals.handlers import Handler, register
from app.Settings import business
from app.Settings.model import SettingVersion
from app.Settings.registry import EVENT_DATE, SOURCES, definition, normalise
from app.Transactions.ledger import locked_through
from app.database.database import db
from app.utils.dates import parse_date, today_eat, utcnow
from app.utils.http import ValidationError


def request_type_for(key: str) -> str:
    return "settings.change_security" if definition(key).approvals_required >= 2 else "settings.change"


class _SettingChange(Handler):
    entity_type = "setting"
    submit_permission = "settings.business.edit"

    def entity_id(self, payload):
        return payload["key"]

    def validate(self, payload):
        key = payload.get("key") or ""
        d = definition(key)
        if request_type_for(key) != self.request_type:
            raise ValidationError(f"{key} must be changed with {request_type_for(key)}.")
        if "value" not in payload:
            raise ValidationError("value is required.")
        value = normalise(key, payload["value"])
        scope_type = payload.get("scope_type") or "global"
        if scope_type not in d.scopes:
            raise ValidationError(f"{key} can't be set per {scope_type}.")
        scope_id = payload.get("scope_id")
        if scope_type == "global":
            scope_id = None
        elif not isinstance(scope_id, int):
            raise ValidationError("scope_id is required for a branch or product setting.")
        effective = parse_date(payload.get("effective_from"), "effective_from", required=False) or today_eat()
        if effective < today_eat():
            raise ValidationError("effective_from can't be in the past; settings are never changed retroactively.")
        locked = locked_through()
        if d.binding == EVENT_DATE and locked is not None and effective <= locked:
            raise ValidationError(f"effective_from falls in an approved interest month (locked through "
                                  f"{locked.isoformat()}). Use a later date.")
        source = payload.get("source") or "client_confirmed"
        if source not in SOURCES:
            raise ValidationError(f"source must be one of: {', '.join(SOURCES)}.")
        evidence = (payload.get("evidence") or "").strip() or None
        if source == "client_confirmed" and not evidence:
            raise ValidationError("evidence is required for a client-confirmed value (e.g. the questionnaire answer).")
        return {"key": key, "value": value, "effective_from": effective.isoformat(), "scope_type": scope_type,
                "scope_id": scope_id, "source": source, "evidence": evidence}

    def _in_force(self, payload):
        scope = None if payload["scope_type"] == "global" else (payload["scope_type"], payload["scope_id"])
        return business.current_version(payload["key"], date.fromisoformat(payload["effective_from"]), scope)

    def base_version(self, payload):
        latest = (SettingVersion.query.filter_by(key=payload["key"], scope_type=payload["scope_type"])
                  .order_by(SettingVersion.id.desc()).first())
        return str(latest.id) if latest else "none"

    def old_value(self, payload):
        row = self._in_force(payload)
        return row.to_dict() if row else None

    def describe(self, payload):
        return f"Set {payload['key']} to {payload['value']} from {payload['effective_from']} ({payload['source']})"

    def apply(self, request, actor):
        p = request.payload
        clash = SettingVersion.query.filter_by(key=p["key"], scope_type=p["scope_type"], scope_id=p["scope_id"],
                                               effective_from=date.fromisoformat(p["effective_from"])).first()
        if clash is not None:
            raise ValidationError("A version with this effective date already exists. Choose another date.")
        row = SettingVersion(
            key=p["key"], scope_type=p["scope_type"], scope_id=p["scope_id"], value=p["value"],
            effective_from=date.fromisoformat(p["effective_from"]),
            version_no=business.next_version_no(p["key"], p["scope_type"], p["scope_id"]),
            source=p["source"], evidence=p["evidence"], reason=request.reason, change_request_id=request.id,
            created_by=request.maker_email, approved_by=actor.email, approved_at=utcnow(),
        )
        db.session.add(row)
        db.session.flush()
        business.clear_cache()
        return {"setting_version_id": row.id, "version_no": row.version_no}


@register
class SettingChange(_SettingChange):
    request_type = "settings.change"


@register
class SecuritySettingChange(_SettingChange):
    request_type = "settings.change_security"
