"""
Periodic scheduling without a scheduler process.

Every worker calls tick() every few seconds. For each periodic task it takes
the periodic_tasks row lock (SKIP LOCKED: another worker is already on it),
works out the slots due since last_slot, and enqueues one job per slot with
dedupe_key "<task>:<slot>". The unique (name, dedupe_key) index makes a slot
enqueue exactly once, whatever the number of workers or web processes.

After downtime, a "latest" task runs once for the most recent missed slot; an
"each" task runs every missed slot in order (capped at MAX_CATCH_UP).
"""
import calendar
import logging
from datetime import datetime, timedelta, timezone

from flask import current_app
from sqlalchemy.exc import IntegrityError

from app.database.database import db
from app.Jobs.model import PeriodicTask
from app.Jobs.queue import enqueue
from app.Jobs.registry import PERIODIC, PERIODIC_BY_NAME, Periodic
from app.utils.dates import utcnow

logger = logging.getLogger(__name__)

MAX_CATCH_UP = 36
EPOCH = datetime(2000, 1, 1, tzinfo=timezone.utc)


def _slot_on_or_before(p: Periodic, spec: dict, t: datetime) -> datetime:
    if p.kind == "interval":
        step = timedelta(minutes=spec["minutes"])
        return EPOCH + ((t - EPOCH) // step) * step
    if p.kind == "daily":
        slot = t.replace(hour=spec["hour"], minute=spec["minute"], second=0, microsecond=0)
        return slot if slot <= t else slot - timedelta(days=1)
    if p.kind == "monthly":
        year, month = t.year, t.month
        for _ in range(2):
            day = min(spec["day"], calendar.monthrange(year, month)[1])
            slot = datetime(year, month, day, spec["hour"], spec["minute"], tzinfo=timezone.utc)
            if slot <= t:
                return slot
            year, month = (year, month - 1) if month > 1 else (year - 1, 12)
        raise AssertionError("unreachable")
    raise ValueError(f"Unknown schedule kind {p.kind}")


def _next_after(p: Periodic, spec: dict, slot: datetime) -> datetime:
    if p.kind == "interval":
        return slot + timedelta(minutes=spec["minutes"])
    if p.kind == "daily":
        return slot + timedelta(days=1)
    year, month = (slot.year, slot.month + 1) if slot.month < 12 else (slot.year + 1, 1)
    day = min(spec["day"], calendar.monthrange(year, month)[1])
    return datetime(year, month, day, spec["hour"], spec["minute"], tzinfo=timezone.utc)


def due_slots(p: Periodic, spec: dict, last_slot: datetime, now: datetime) -> list[datetime]:
    """Slots strictly after last_slot and at or before now, oldest first."""
    latest = _slot_on_or_before(p, spec, now)
    if latest <= last_slot:
        return []
    if p.catch_up == "latest":
        return [latest]
    slots, slot = [], _next_after(p, spec, _slot_on_or_before(p, spec, last_slot))
    while slot <= latest:
        if slot > last_slot:
            slots.append(slot)
        slot = _next_after(p, spec, slot)
    return slots[-MAX_CATCH_UP:]


def next_slot(p: Periodic, spec: dict, now: datetime) -> datetime:
    return _next_after(p, spec, _slot_on_or_before(p, spec, now))


def tick(now: datetime | None = None, app=None) -> int:
    """Enqueue due periodic jobs. Safe to call from any number of processes at once."""
    app = app or current_app._get_current_object()
    now = now or utcnow()
    enqueued = 0
    for p in PERIODIC:
        row = (db.session.query(PeriodicTask).filter(PeriodicTask.name == p.name)
               .with_for_update(skip_locked=True).first())
        if row is None:
            if db.session.get(PeriodicTask, p.name) is not None:
                db.session.rollback()
                continue  # another process holds it right now
            # A periodic task added in code after deployment starts from now (no backfill).
            db.session.add(PeriodicTask(name=p.name, last_slot=now))
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()  # another process created it first
            continue
        try:
            spec = p.spec(app)
            slots = due_slots(p, spec, row.last_slot, now)
            if p.enabled(app):
                for slot in slots:
                    if enqueue(p.task, p.args(slot), dedupe_key=f"{p.name}:{slot.isoformat()}",
                               enqueued_by="scheduler", run_at=now) is not None:
                        enqueued += 1
            if slots:
                row.last_slot = slots[-1]
            row.next_slot = next_slot(p, spec, now) if p.enabled(app) else None
            row.last_ticked_at = now
            db.session.commit()
        except Exception:
            db.session.rollback()
            logger.error("Scheduling %s failed", p.name, exc_info=True)
    return enqueued


def next_run(name: str) -> str | None:
    """When a periodic task next runs (for the Emails, Settings and Backups screens)."""
    row = db.session.get(PeriodicTask, name)
    p = PERIODIC_BY_NAME.get(name)
    if row is None or p is None:
        return None
    app = current_app._get_current_object()
    if not p.enabled(app):
        return None
    return next_slot(p, p.spec(app), max(utcnow(), row.last_slot)).isoformat()
