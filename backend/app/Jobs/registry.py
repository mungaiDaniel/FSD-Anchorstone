"""
What the worker can run, and what runs on a schedule.

    @task("email.drain", queue="email")
    def drain(args): ...

    PERIODIC: each entry enqueues one job per slot. Slots are UTC.
        interval  every N minutes, aligned to the clock
        daily     at HH:MM
        monthly   on day D at HH:MM
    catch_up = "latest": after downtime, run once for the most recent missed slot
    catch_up = "each":   run every missed slot in order (e.g. each missed month)
"""
from dataclasses import dataclass
from typing import Callable

TASKS: dict[str, "TaskDef"] = {}


@dataclass(frozen=True)
class TaskDef:
    name: str
    fn: Callable[[dict], object]
    queue: str
    max_attempts: int
    timeout_seconds: int  # a running job silent for longer is presumed dead and reclaimed
    # A task that processes a client's personal data for a consent-based purpose (e.g. AI document
    # reading) declares it; the job is refused at enqueue and at run without that client's consent.
    consent_purpose: str | None = None
    # Called (args, message) when a queued job is refused at run time because the consent was withdrawn
    # meanwhile, so the task can close its own record. The job fails at once (retrying can't help).
    on_consent_refused: Callable[[dict, str], None] | None = None


def task(name: str, queue: str = "default", max_attempts: int = 3, timeout_seconds: int = 600,
         consent_purpose: str | None = None, on_consent_refused: Callable[[dict, str], None] | None = None):
    def decorator(fn):
        if name in TASKS:
            raise TypeError(f"Duplicate task {name}")
        TASKS[name] = TaskDef(name, fn, queue, max_attempts, timeout_seconds, consent_purpose, on_consent_refused)
        return fn
    return decorator


@dataclass(frozen=True)
class Periodic:
    name: str               # periodic_tasks.name, also shown as the job id on screens
    task: str               # TASKS key
    kind: str               # interval / daily / monthly
    spec: Callable          # app -> {"minutes": n} | {"hour", "minute"} | {"day", "hour", "minute"}
    catch_up: str = "latest"
    enabled: Callable = lambda app: True
    args: Callable = lambda slot: {}


def _email_interval(app):
    from app.database.database import db
    from app.Settings.service import get_effective_email_settings
    return {"minutes": int(get_effective_email_settings(app, db.session).get("email_queue_interval_minutes") or 2)}


PERIODIC = [
    Periodic("email.drain", "email.drain", "interval", _email_interval),
    Periodic("email.recover_stuck", "email.recover_stuck", "interval", lambda app: {"minutes": 5}),
    # 1st of each month, 07:00 Nairobi (04:00 UTC). Each missed month is generated in turn.
    Periodic("reports.aum_monthly", "reports.aum_monthly", "monthly", lambda app: {"day": 1, "hour": 4, "minute": 0},
             catch_up="each", args=lambda slot: {"slot": slot.isoformat()}),
    Periodic("backup.daily", "backup.run", "daily",
             lambda app: {"hour": int(app.config["DB_BACKUP_HOUR_UTC"]), "minute": int(app.config["DB_BACKUP_MINUTE_UTC"])},
             enabled=lambda app: bool(app.config.get("DB_BACKUP_ENABLED")),
             args=lambda slot: {"triggered_by": "scheduled"}),
    Periodic("change_requests.expire", "change_requests.expire", "interval", lambda app: {"minutes": 60}),
    # Daily at 02:00 Nairobi (23:00 UTC): existing clients against the watchlists.
    Periodic("screening.rescreen", "screening.rescreen", "daily", lambda app: {"hour": 23, "minute": 0}),
    # Daily at 01:00 Nairobi (22:00 UTC), before the re-screen: the UN sanctions list. The job does nothing
    # while screening.un_sanctions.import_enabled is off.
    Periodic("screening.un_sanctions_import", "screening.un_sanctions_import", "daily",
             lambda app: {"hour": 22, "minute": 0}),
]
PERIODIC_BY_NAME = {p.name: p for p in PERIODIC}


def load_tasks() -> None:
    import app.Jobs.tasks  # noqa: F401
