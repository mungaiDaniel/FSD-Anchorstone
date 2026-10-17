"""
The posting engine. Business code records an event; the engine builds the
journal from the posting rule in force on the event's value date:

    from app.Ledger import engine
    entry = engine.post("INV_DEPOSIT_POSTED", source=("deposit", deposit.id), value_date=deposit.value_date,
                        branch_id=investor.branch_id, amounts={"amount": deposit.amount},
                        refs={"investment_account": investor.account_id}, actor_email=actor_email())
    create_audit_log(...)
    db.session.commit()          # the business change, its journal and its audit entry together

post() never commits. Each event has a unique source key (event type, source
type, source id, occurrence): posting the same event again is refused with
Conflict, never duplicated, and an advisory lock makes that hold under
concurrency too. An amount of zero leaves out the lines that take it (e.g.
withholding tax at 0%).
"""
import re
from datetime import date

from sqlalchemy import text

from app.database.database import db
from app.Ledger import journals, rules
from app.Ledger.model import EVENT_TYPE_PATTERN, GlEvent, JournalEntry
from app.utils.dates import today_eat
from app.utils.http import Conflict, ValidationError
from app.utils.money import as_str


def source_key(event_type: str, source_type: str, source_id, occurrence: int = 1) -> str:
    return f"{event_type}:{source_type}:{source_id}:{occurrence}"


def find_event(event_type: str, source: tuple[str, object], occurrence: int = 1) -> GlEvent | None:
    return GlEvent.query.filter_by(event_type=event_type, source_type=source[0], source_id=str(source[1]),
                                   occurrence=occurrence).first()


def _source(source) -> tuple[str, str]:
    if not (isinstance(source, tuple) and len(source) == 2 and isinstance(source[0], str) and source[0].strip()
            and source[1] is not None and str(source[1]).strip()):
        raise ValidationError("source must be (source_type, source_id).")
    if len(source[0]) > 40 or len(str(source[1])) > 64:
        raise ValidationError("source_type or source_id is too long.")
    return source[0].strip(), str(source[1]).strip()


def post(event_type: str, *, source: tuple[str, object], value_date: date, branch_id: int, amounts: dict,
         refs: dict | None = None, actor_email: str, description: str | None = None,
         occurrence: int = 1) -> JournalEntry:
    if not isinstance(event_type, str) or not re.match(EVENT_TYPE_PATTERN, event_type):
        raise ValidationError("event_type must be an UPPER_SNAKE event code.")
    source_type, source_id = _source(source)
    if not isinstance(occurrence, int) or isinstance(occurrence, bool) or occurrence < 1:
        raise ValidationError("occurrence must be a whole number from 1.")
    if not isinstance(value_date, date):
        raise ValidationError("value_date is required.")
    if value_date > today_eat():
        raise ValidationError("An event can't be posted with a future value date.")
    refs = dict(refs or {})
    if not isinstance(amounts, dict) or not amounts:
        raise ValidationError("amounts are required.")

    key = source_key(event_type, source_type, source_id, occurrence)
    # Serialise posts of the same key; the second one then sees the first and is refused.
    db.session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"), {"k": key})
    existing = find_event(event_type, (source_type, source_id), occurrence)
    if existing is not None:
        entry = db.session.get(JournalEntry, existing.journal_entry_id)
        raise Conflict(f"{key} was already posted as {entry.journal_no}.")

    rule = rules.in_force(event_type, value_date)
    if rule is None:
        raise ValidationError(f"No posting rule for {event_type} is in force on {value_date.isoformat()}.")
    fields = {line.amount_field for line in rule.lines}
    unknown = set(amounts) - fields
    if unknown:
        raise ValidationError(f"{event_type} has no use for {', '.join(sorted(unknown))}.")
    missing = fields - set(amounts)
    if missing:
        raise ValidationError(f"{event_type} needs {', '.join(sorted(missing))}.")
    clean = {f: journals.money(amounts[f], f) for f in fields}
    if not any(clean.values()):
        raise ValidationError("Every amount is zero; there is nothing to post.")

    lines = []
    for line in rule.lines:
        amount = clean[line.amount_field]
        if not amount:
            continue
        account_id = None
        if line.account_ref:
            account_id = refs.get(line.account_ref)
            if account_id is None:
                raise ValidationError(f"{event_type} needs the reference {line.account_ref}.")
        lines.append({"gl_account_id": line.gl_account_id, line.side: amount, "account_id": account_id,
                      "party_id": refs.get("party_id") if line.account_ref else None,
                      "description": line.description})

    entry = journals.write_entry(
        value_date=value_date, branch_id=branch_id,
        description=description or rule.description, lines=lines, created_by=actor_email,
        event_type=event_type, source=(source_type, source_id), posting_rule_id=rule.id)
    db.session.add(GlEvent(event_type=event_type, source_type=source_type, source_id=source_id,
                           occurrence=occurrence, value_date=value_date, branch_id=entry.branch_id,
                           amounts={f: as_str(v) for f, v in clean.items()}, refs=refs, posting_rule_id=rule.id,
                           journal_entry_id=entry.id, created_by=actor_email))
    db.session.flush()
    return entry


def reverse(entry_id: int, reason: str, actor_email: str) -> JournalEntry:
    """Reverse a posted entry (mirror lines, linked by reversal_of). Never commits."""
    return journals.reverse(entry_id, reason, actor_email)
