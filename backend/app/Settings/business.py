"""
Reading business-rule settings.

    get("security.login_max_failures")                               today, global
    get("investments.wht_rate_percent", as_of=period.period_end)     value in force on that date
    get("lending.penalty_grace_days", scope=("product", 12))         product override → global

Resolution: the most specific scope with a version whose effective_from ≤ as_of,
then the next broader scope (product → branch → global), then the registry
default (only before the key is seeded; logged). Values are cached for the
current request.
"""
import logging
from datetime import date
from decimal import Decimal

from flask import g, has_app_context

from app.database.database import db
from app.Settings.model import SettingVersion
from app.Settings.registry import REGISTRY, definition
from app.utils.dates import today_eat

logger = logging.getLogger(__name__)


def _typed(key: str, value):
    return Decimal(value) if definition(key).type == "decimal" else value


def current_version(key: str, as_of: date | None = None, scope: tuple[str, int] | None = None) -> SettingVersion | None:
    definition(key)
    as_of = as_of or today_eat()
    chain = [scope] if scope and scope[0] != "global" else []
    chain.append(("global", None))
    for scope_type, scope_id in chain:
        q = SettingVersion.query.filter(SettingVersion.key == key, SettingVersion.scope_type == scope_type,
                                        SettingVersion.effective_from <= as_of)
        q = q.filter(SettingVersion.scope_id.is_(None)) if scope_id is None else q.filter(SettingVersion.scope_id == scope_id)
        row = q.order_by(SettingVersion.effective_from.desc(), SettingVersion.version_no.desc()).first()
        if row is not None:
            return row
    return None


def get(key: str, as_of: date | None = None, scope: tuple[str, int] | None = None):
    as_of = as_of or today_eat()
    cache = getattr(g, "_settings_cache", None) if has_app_context() else None
    cache_key = (key, as_of, scope)
    if cache is not None and cache_key in cache:
        return cache[cache_key]
    row = current_version(key, as_of, scope)
    if row is None:
        logger.warning("Setting %s has no version in force on %s; using the registry default.", key, as_of)
        value = REGISTRY[key].default
    else:
        value = row.value
    value = _typed(key, value)
    if has_app_context():
        g.setdefault("_settings_cache", {})[cache_key] = value
    return value


def clear_cache() -> None:
    if has_app_context():
        g.pop("_settings_cache", None)


def next_version_no(key: str, scope_type: str, scope_id: int | None) -> int:
    q = db.session.query(db.func.max(SettingVersion.version_no)).filter(
        SettingVersion.key == key, SettingVersion.scope_type == scope_type)
    q = q.filter(SettingVersion.scope_id.is_(None)) if scope_id is None else q.filter(SettingVersion.scope_id == scope_id)
    return (q.scalar() or 0) + 1


def overview(source: str | None = None) -> list[dict]:
    """Every key with its value in force today, its source and history (for the Business rules page)."""
    out = []
    for d in REGISTRY.values():
        row = current_version(d.key)
        if source and (row.source if row else "working_assumption") != source:
            continue
        history = (SettingVersion.query.filter_by(key=d.key)
                   .order_by(SettingVersion.effective_from.desc(), SettingVersion.version_no.desc()).all())
        out.append({
            "key": d.key, "category": d.category, "type": d.type, "description": d.description,
            "binding": d.binding, "scopes": list(d.scopes), "approvals_required": d.approvals_required,
            "in_use": d.in_use, "wa_ref": d.wa_ref, "questionnaire_ref": d.questionnaire_ref,
            "choices": list(d.choices), "default": d.default,
            "value": row.value if row else d.default,
            "source": row.source if row else None,
            "effective_from": row.effective_from.isoformat() if row else None,
            "history": [h.to_dict() for h in history],
        })
    return out
