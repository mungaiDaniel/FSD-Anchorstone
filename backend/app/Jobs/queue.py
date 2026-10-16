"""
The job queue API. The backend behind it (a table claimed with SKIP LOCKED) can
be swapped without changing callers.

    enqueue(name, args, ...)   adds a row WITHOUT committing: the caller commits
                               it with the business change, so either both
                               exist or neither does
    claim(worker_id, queues)   takes the next due job (one worker per job)
    run(job_id, worker_id)     runs it; success → succeeded, error → retried
                               with backoff, then failed
    reclaim_stale(now)         a running job whose worker stopped heart-beating
                               is put back in the queue (restartable)
"""
import logging
import threading
import traceback
from datetime import datetime, timedelta

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert

from app.database.database import db
from app.Jobs.model import JOB_FAILED, JOB_QUEUED, JOB_RUNNING, JOB_SUCCEEDED, Job
from app.Jobs.registry import TASKS
from app.utils.dates import utcnow
from app.utils.http import ValidationError

logger = logging.getLogger(__name__)

HEARTBEAT_SECONDS = 20
BACKOFF_BASE_SECONDS = 30
BACKOFF_MAX_SECONDS = 3600


def enqueue(name: str, args: dict | None = None, *, run_at: datetime | None = None, dedupe_key: str | None = None,
            priority: int = 0, enqueued_by: str = "system") -> int | None:
    """Add a job to the current transaction. Returns its id, or None if dedupe_key already exists."""
    task = TASKS.get(name)
    if task is None:
        raise ValidationError(f"Unknown job: {name}.")
    stmt = insert(Job.__table__).values(
        name=name, queue=task.queue, args=args or {}, status=JOB_QUEUED, priority=priority,
        run_at=run_at or utcnow(), attempts=0, max_attempts=task.max_attempts, dedupe_key=dedupe_key,
        enqueued_by=enqueued_by, date_created=utcnow(), date_updated=utcnow(),
    )
    if dedupe_key is not None:
        stmt = stmt.on_conflict_do_nothing(index_elements=["name", "dedupe_key"],
                                           index_where=text("dedupe_key IS NOT NULL"))
    return db.session.execute(stmt.returning(Job.__table__.c.id)).scalar()


def claim(worker_id: str, queues: list[str] | None = None, now: datetime | None = None) -> int | None:
    """Mark the next due job running for this worker and commit. Returns its id."""
    now = now or utcnow()
    params = {"w": worker_id, "now": now}
    queue_filter = ""
    if queues:
        queue_filter = "AND queue = ANY(:queues)"
        params["queues"] = list(queues)
    job_id = db.session.execute(text(f"""
        UPDATE jobs SET status = 'running', locked_by = :w, locked_at = :now, heartbeat_at = :now,
                        attempts = attempts + 1, date_updated = :now
        WHERE id = (SELECT id FROM jobs WHERE status = 'queued' AND run_at <= :now {queue_filter}
                    ORDER BY priority DESC, run_at, id FOR UPDATE SKIP LOCKED LIMIT 1)
        RETURNING id"""), params).scalar()
    db.session.commit()
    return job_id


def _beat(app, job_id: int, worker_id: str, stop: threading.Event) -> None:
    """Keep heartbeat_at fresh from a side connection while a long job runs."""
    with app.app_context():
        engine = db.engine
        while not stop.wait(HEARTBEAT_SECONDS):
            try:
                with engine.begin() as conn:
                    conn.execute(text("UPDATE jobs SET heartbeat_at = now() WHERE id = :id AND locked_by = :w "
                                      "AND status = 'running'"), {"id": job_id, "w": worker_id})
            except Exception:
                logger.warning("Heartbeat for job %s failed", job_id, exc_info=True)


def backoff(attempts: int) -> timedelta:
    return timedelta(seconds=min(BACKOFF_BASE_SECONDS * 2 ** max(attempts - 1, 0), BACKOFF_MAX_SECONDS))


def run(job_id: int, worker_id: str, app=None) -> str:
    """Run a claimed job and record the outcome. Returns the final status."""
    job = db.session.get(Job, job_id)
    task = TASKS.get(job.name)
    stop = threading.Event()
    beat = None
    if app is not None:
        beat = threading.Thread(target=_beat, args=(app, job_id, worker_id, stop), daemon=True)
        beat.start()
    try:
        if task is None:
            raise RuntimeError(f"No task registered for {job.name}")
        result = task.fn(dict(job.args or {}))
        db.session.commit()  # whatever the task left uncommitted
        status, error = JOB_SUCCEEDED, None
    except Exception as e:
        db.session.rollback()
        logger.error("Job %s (%s) failed", job_id, job.name if job else "?", exc_info=True)
        result, error = None, f"{type(e).__name__}: {e}\n{traceback.format_exc(limit=5)}"[:4000]
        status = JOB_FAILED
    finally:
        stop.set()
        if beat is not None:
            beat.join(timeout=5)

    job = db.session.get(Job, job_id)
    db.session.refresh(job)
    now = utcnow()
    if job.status != JOB_RUNNING or job.locked_by != worker_id:
        # Reclaimed by another worker while we ran: leave its record alone.
        logger.warning("Job %s was reclaimed while running on %s", job_id, worker_id)
        return job.status
    if status == JOB_SUCCEEDED:
        job.status, job.result, job.finished_at, job.last_error = JOB_SUCCEEDED, _jsonable(result), now, None
    elif job.attempts < job.max_attempts:
        job.status, job.run_at, job.last_error = JOB_QUEUED, now + backoff(job.attempts), error
    else:
        job.status, job.finished_at, job.last_error = JOB_FAILED, now, error
    job.locked_by = None
    db.session.commit()
    return job.status


def _jsonable(value):
    if value is None or isinstance(value, (dict, list, str, int, float, bool)):
        return value
    return {"value": str(value)}


def reclaim_stale(now: datetime | None = None) -> int:
    """Re-queue running jobs whose worker went silent for longer than the task's timeout."""
    now = now or utcnow()
    count = 0
    running = db.session.query(Job).filter(Job.status == JOB_RUNNING).with_for_update(skip_locked=True).all()
    for job in running:
        task = TASKS.get(job.name)
        timeout = timedelta(seconds=max(task.timeout_seconds if task else 600, HEARTBEAT_SECONDS * 3))
        if job.heartbeat_at is None or job.heartbeat_at < now - timeout:
            job.last_error = f"Reclaimed: worker {job.locked_by} stopped responding."
            job.locked_by = None
            if job.attempts < job.max_attempts:
                job.status, job.run_at = JOB_QUEUED, now
            else:
                job.status, job.finished_at = JOB_FAILED, now
            count += 1
    db.session.commit()
    return count
