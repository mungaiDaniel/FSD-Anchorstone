"""
Posting rules: event type -> journal lines (account, debit or credit, which
amount of the event, and for control accounts which reference names the
client account).

Rules are versioned data. A version is never changed: a new one is added
through the gl.posting_rule.change change request, dated today or later, and
the engine uses the version in force on the event's value date.

A rule is balanced by construction: for every amount field, it has as many
debit lines as credit lines, so any set of amounts produces a balanced entry.
"""
import re
from collections import Counter
from datetime import date

from sqlalchemy import func

from app.database.database import db
from app.Ledger.model import (ACCOUNT_SOURCES, EVENT_TYPE_PATTERN, FIELD_PATTERN, SIDES, GlAccount, PostingRule,
                              PostingRuleLine)
from app.utils.dates import parse_date, today_eat
from app.utils.http import NotFound, ValidationError


def in_force(event_type: str, as_of: date) -> PostingRule | None:
    return (PostingRule.query.filter(PostingRule.event_type == event_type, PostingRule.effective_from <= as_of)
            .order_by(PostingRule.effective_from.desc()).first())


def latest(event_type: str) -> PostingRule | None:
    return (PostingRule.query.filter(PostingRule.event_type == event_type)
            .order_by(PostingRule.version_no.desc()).first())


def get_rule(rule_id) -> PostingRule:
    rule = db.session.get(PostingRule, rule_id) if isinstance(rule_id, int) else None
    if rule is None:
        raise NotFound("Posting rule not found.")
    return rule


def current_rules() -> list[PostingRule]:
    """The latest version of every event type."""
    latest_ids = (db.session.query(func.max(PostingRule.id)).group_by(PostingRule.event_type))
    return PostingRule.query.filter(PostingRule.id.in_(latest_ids)).order_by(PostingRule.event_type).all()


def history(event_type: str | None = None) -> list[PostingRule]:
    q = PostingRule.query
    if event_type:
        q = q.filter(PostingRule.event_type == event_type)
    return q.order_by(PostingRule.event_type, PostingRule.version_no.desc()).all()


def accounts_in_use() -> set[int]:
    """GL accounts named by a rule version in force today or taking effect later (they can't be deactivated)."""
    today = today_eat()
    ids = []
    for rule in current_rules():
        live = in_force(rule.event_type, today)
        ids += [r.id for r in history(rule.event_type) if live is None or r.effective_from >= live.effective_from]
    if not ids:
        return set()
    return {row[0] for row in db.session.query(PostingRuleLine.gl_account_id)
            .filter(PostingRuleLine.rule_id.in_(ids)).distinct()}


def _text(value, field, pattern=None, required=True, max_len=1000):
    if value is not None and not isinstance(value, str):
        raise ValidationError(f"{field} must be text.")
    value = (value or "").strip()
    if required and not value:
        raise ValidationError(f"{field} is required.")
    if len(value) > max_len:
        raise ValidationError(f"{field} must be at most {max_len} characters.")
    if value and pattern and not re.match(pattern, value):
        raise ValidationError(f"{field} {value!r} isn't valid.")
    return value or None


def validate_definition(payload: dict) -> dict:
    """Normalise a proposed rule version. Raises ValidationError."""
    event_type = _text(payload.get("event_type"), "event_type", EVENT_TYPE_PATTERN, max_len=60)
    effective = parse_date(payload.get("effective_from"), "effective_from", required=False) or today_eat()
    if effective < today_eat():
        raise ValidationError("effective_from can't be in the past; journals already posted keep their rule.")
    if PostingRule.query.filter_by(event_type=event_type, effective_from=effective).first() is not None:
        raise ValidationError(f"A version of {event_type} already takes effect on {effective.isoformat()}.")
    source = payload.get("source") or "internal_decision"
    if source not in ACCOUNT_SOURCES:
        raise ValidationError(f"source must be one of: {', '.join(ACCOUNT_SOURCES)}.")
    lines = payload.get("lines")
    if not isinstance(lines, list) or len(lines) < 2:
        raise ValidationError("A posting rule needs at least two lines.")
    out, balance = [], Counter()
    for n, line in enumerate(lines, 1):
        if not isinstance(line, dict):
            raise ValidationError(f"Line {n} must be an object.")
        side = line.get("side")
        if side not in SIDES:
            raise ValidationError(f"Line {n}: side must be debit or credit.")
        gl_id = line.get("gl_account_id")
        account = db.session.get(GlAccount, gl_id) if isinstance(gl_id, int) and not isinstance(gl_id, bool) else None
        if account is None:
            raise ValidationError(f"Line {n}: unknown GL account.")
        if not account.is_postable or not account.is_active:
            raise ValidationError(f"Line {n}: {account.code} {account.name} can't take postings "
                                  f"({'header' if not account.is_postable else 'inactive'}).")
        field = _text(line.get("amount_field"), f"Line {n} amount_field", FIELD_PATTERN, max_len=40)
        ref = _text(line.get("account_ref"), f"Line {n} account_ref", FIELD_PATTERN, required=False, max_len=40)
        if account.is_control and not ref:
            raise ValidationError(f"Line {n}: {account.code} is a control account; name the account_ref that "
                                  "identifies the client account.")
        if not account.is_control and ref:
            raise ValidationError(f"Line {n}: {account.code} isn't a control account; it takes no account_ref.")
        balance[field] += 1 if side == "debit" else -1
        out.append({"side": side, "gl_account_id": account.id, "amount_field": field, "account_ref": ref,
                    "description": _text(line.get("description"), f"Line {n} description", required=False,
                                         max_len=200)})
    unbalanced = sorted(f for f, n in balance.items() if n)
    if unbalanced:
        raise ValidationError(f"The rule doesn't balance: {', '.join(unbalanced)} must appear on as many debit "
                              "lines as credit lines.")
    return {"event_type": event_type, "effective_from": effective.isoformat(), "source": source,
            "description": _text(payload.get("description"), "description"), "lines": out}
