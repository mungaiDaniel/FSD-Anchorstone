"""
Writing journals. Ledger-internal: business code calls app.Ledger.engine.post()
(an event and its posting rule), never this module, and a test fails if
JournalLine is built anywhere outside app/Ledger.

Nothing here commits. The caller commits the entry together with the business
change and its audit entry. The checks below give readable errors; the
database triggers are the guarantee (see app/Ledger/model.py).
"""
from datetime import date
from decimal import Decimal, InvalidOperation

from app.Branches.model import CURRENCY, Branch
from app.database.database import db
from app.Ledger import periods
from app.Ledger.model import GlAccount, JournalEntry, JournalLine
from app.Parties.model import Account
from app.utils.dates import today_eat, utcnow
from app.utils.http import Conflict, NotFound, ValidationError
from app.utils.money import fmt_kes

ZERO = Decimal("0")


def money(value, field: str) -> Decimal:
    """A line amount: Decimal, string or int; never float; at most 2 decimal places; not negative."""
    if value is None:
        return ZERO
    if isinstance(value, (float, bool)) or not isinstance(value, (Decimal, str, int)):
        raise ValidationError(f"{field} must be a decimal string, e.g. \"1250.00\".")
    try:
        amount = Decimal(str(value).replace(",", "").strip() or "0")
    except InvalidOperation:
        raise ValidationError(f"{field} must be a number.")
    if not amount.is_finite() or amount < 0:
        raise ValidationError(f"{field} can't be negative.")
    if amount.as_tuple().exponent < -2:
        raise ValidationError(f"{field} has more than 2 decimal places.")
    return amount.quantize(Decimal("0.01"))


def _branch(branch_id) -> int:
    branch = db.session.get(Branch, branch_id) if isinstance(branch_id, int) else None
    if branch is None:
        raise ValidationError("branch_id must be an existing branch.")
    return branch.id


def normalise_lines(lines, entry_branch_id: int) -> list[dict]:
    if not isinstance(lines, list) or len(lines) < 2:
        raise ValidationError("A journal entry needs at least two lines.")
    out, debits, credits = [], ZERO, ZERO
    for n, line in enumerate(lines, 1):
        where = f"Line {n}"
        account = db.session.get(GlAccount, line.get("gl_account_id")) \
            if isinstance(line.get("gl_account_id"), int) else None
        if account is None:
            raise ValidationError(f"{where}: unknown GL account.")
        label = f"{where} ({account.code} {account.name})"
        if not account.is_postable:
            raise ValidationError(f"{label} is a header account and can't take postings.")
        if not account.is_active:
            raise ValidationError(f"{label} is inactive.")
        debit, credit = money(line.get("debit"), f"{where} debit"), money(line.get("credit"), f"{where} credit")
        if (debit > 0) == (credit > 0):
            raise ValidationError(f"{where} needs exactly one of debit or credit, greater than zero.")
        branch_id = _branch(line.get("branch_id", entry_branch_id))
        if account.branch_id is not None and account.branch_id != branch_id:
            raise ValidationError(f"{label} belongs to another branch.")
        account_id = line.get("account_id")
        if account.is_control and account_id is None:
            raise ValidationError(f"{label} is a control account; the line must name the client account.")
        if not account.is_control and account_id is not None:
            raise ValidationError(f"{label} isn't a control account; the line can't name a client account.")
        if account_id is not None and (not isinstance(account_id, int) or db.session.get(Account, account_id) is None):
            raise ValidationError(f"{where}: unknown client account.")
        debits, credits = debits + debit, credits + credit
        out.append({"gl_account_id": account.id, "debit": debit, "credit": credit, "branch_id": branch_id,
                    "account_id": account_id, "party_id": line.get("party_id"),
                    "description": (line.get("description") or None)})
    if debits != credits:
        raise ValidationError(f"The entry doesn't balance: debits {fmt_kes(debits)}, credits {fmt_kes(credits)}.")
    return out


def write_entry(*, value_date: date, branch_id: int, description: str, lines: list[dict], created_by: str,
                event_type: str | None = None, source: tuple[str, str] | None = None,
                reversal_of: int | None = None, reason: str | None = None) -> JournalEntry:
    if not isinstance(value_date, date):
        raise ValidationError("value_date is required.")
    if not (description or "").strip():
        raise ValidationError("A journal entry needs a description.")
    branch_id = _branch(branch_id)
    clean = normalise_lines(lines, branch_id)
    period = periods.lock_open(value_date, created_by)
    entry = JournalEntry(
        entry_date=today_eat(), value_date=value_date, period_id=period.id, branch_id=branch_id, currency=CURRENCY,
        description=description.strip(), event_type=event_type,
        source_type=source[0] if source else None, source_id=str(source[1]) if source else None,
        reversal_of=reversal_of, reason=reason, created_by=created_by, posted_at=utcnow(),
    )
    db.session.add(entry)
    db.session.flush()
    for n, line in enumerate(clean, 1):
        db.session.add(JournalLine(entry_id=entry.id, line_no=n, currency=CURRENCY, **line))
    db.session.flush()
    return entry


def get_entry(entry_id) -> JournalEntry:
    entry = db.session.get(JournalEntry, entry_id) if isinstance(entry_id, int) else None
    if entry is None:
        raise NotFound("Journal entry not found.")
    return entry


def reversal_of(entry: JournalEntry) -> JournalEntry | None:
    return JournalEntry.query.filter(JournalEntry.reversal_of == entry.id).first()


def reverse(entry_id: int, reason: str, actor_email: str) -> JournalEntry:
    """
    A new entry mirroring the original (debits and credits swapped), linked by reversal_of.
    It is dated the original's value date while that period is open (as if the original never
    happened, which interest and statements rely on), otherwise today (Nairobi).
    """
    reason = (reason or "").strip() if isinstance(reason, str) or reason is None else ""
    if not reason:
        raise ValidationError("A reversal needs a reason.")
    original = (db.session.query(JournalEntry).filter(JournalEntry.id == entry_id)
                .with_for_update().first()) if isinstance(entry_id, int) else None
    if original is None:
        raise NotFound("Journal entry not found.")
    if original.reversal_of is not None:
        raise ValidationError(f"{original.journal_no} is itself a reversal and can't be reversed.")
    done = reversal_of(original)
    if done is not None:
        raise Conflict(f"{original.journal_no} was already reversed by {done.journal_no}.")
    value_date = original.value_date if periods.is_open(original.value_date) else today_eat()
    lines = [{"gl_account_id": l.gl_account_id, "debit": l.credit, "credit": l.debit, "branch_id": l.branch_id,
              "account_id": l.account_id, "party_id": l.party_id, "description": l.description}
             for l in original.lines]
    return write_entry(value_date=value_date, branch_id=original.branch_id,
                       description=f"Reversal of {original.journal_no}: {original.description}", lines=lines,
                       created_by=actor_email, event_type=original.event_type,
                       source=(original.source_type, original.source_id) if original.source_type else None,
                       reversal_of=original.id, reason=reason)
