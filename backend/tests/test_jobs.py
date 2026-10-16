"""Phase 2a item 5: the PostgreSQL job queue and the worker process."""
import threading
import time
from datetime import datetime, timedelta, timezone

import pytest

from app.database.database import db
from app.Emails.model import STATUS_QUEUED, STATUS_SENDING, STATUS_SENT, OutboxEmail
from app.Emails.sender import mail
from app.Jobs import queue
from app.Jobs.model import Job, PeriodicTask
from app.Jobs.registry import PERIODIC_BY_NAME, TASKS, TaskDef
from app.Jobs.scheduler import due_slots, tick
from app.Jobs.worker import run_worker
from app.utils.dates import utcnow

UTC = timezone.utc
RUNS: list[int] = []
RUNS_LOCK = threading.Lock()


def _count(args):
    time.sleep(args.get("sleep", 0))
    with RUNS_LOCK:
        RUNS.append(args["n"])
    return {"n": args["n"]}


def _boom(args):
    raise RuntimeError("deliberate failure")


TASKS.setdefault("test.count", TaskDef("test.count", _count, "test", 3, 600))
TASKS.setdefault("test.boom", TaskDef("test.boom", _boom, "test", 2, 600))


@pytest.fixture(autouse=True)
def _reset_runs():
    RUNS.clear()


def _jobs(name):
    return Job.query.filter_by(name=name).order_by(Job.id).all()


def _set_last_slot(name, when):
    row = db.session.get(PeriodicTask, name)
    row.last_slot = when
    db.session.commit()


# ── Enqueueing ──


def test_enqueue_belongs_to_the_callers_transaction(app):
    queue.enqueue("test.count", {"n": 1})
    db.session.rollback()
    assert _jobs("test.count") == []
    queue.enqueue("test.count", {"n": 1})
    db.session.commit()
    assert len(_jobs("test.count")) == 1


def test_dedupe_key_enqueues_once():
    assert queue.enqueue("test.count", {"n": 1}, dedupe_key="k") is not None
    assert queue.enqueue("test.count", {"n": 2}, dedupe_key="k") is None
    db.session.commit()
    assert len(_jobs("test.count")) == 1


def test_unknown_job_is_refused():
    from app.utils.http import ValidationError
    with pytest.raises(ValidationError):
        queue.enqueue("no.such.job")


# ── Exactly once across workers ──


def test_two_workers_never_run_the_same_job(app):
    for n in range(12):
        queue.enqueue("test.count", {"n": n, "sleep": 0.05})
    db.session.commit()
    stop = threading.Event()

    def work():
        run_worker(app, ["test"], poll_seconds=0.02, stop=stop)

    workers = [threading.Thread(target=work) for _ in range(2)]
    for w in workers:
        w.start()
    deadline = time.monotonic() + 30
    while len(RUNS) < 12 and time.monotonic() < deadline:
        time.sleep(0.05)
    stop.set()
    for w in workers:
        w.join(timeout=10)
    assert sorted(RUNS) == list(range(12)), "every job ran exactly once"
    db.session.expire_all()
    jobs = _jobs("test.count")
    assert {j.status for j in jobs} == {"succeeded"} and {j.attempts for j in jobs} == {1}


def test_concurrent_claims_of_one_job_give_it_to_one_worker(app):
    job_id = queue.enqueue("test.count", {"n": 1})
    db.session.commit()
    barrier = threading.Barrier(4)
    claimed = []

    def grab(i):
        with app.app_context():
            barrier.wait()
            claimed.append(queue.claim(f"w{i}", ["test"]))
            db.session.remove()

    threads = [threading.Thread(target=grab, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(claimed, key=lambda x: x is None) == [job_id, None, None, None]


def test_four_schedulers_ticking_together_enqueue_each_slot_once(app, monkeypatch):
    monkeypatch.setitem(app.config, "DB_BACKUP_ENABLED", True)
    now = datetime(2026, 10, 2, 6, 0, tzinfo=UTC)
    _set_last_slot("backup.daily", now - timedelta(days=1, hours=1))
    _set_last_slot("reports.aum_monthly", datetime(2026, 9, 1, 4, 0, tzinfo=UTC))
    barrier = threading.Barrier(4)

    def scheduler():
        with app.app_context():
            barrier.wait()
            tick(now=now, app=app)
            db.session.remove()

    threads = [threading.Thread(target=scheduler) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    db.session.expire_all()
    backups = _jobs("backup.run")
    aum = _jobs("reports.aum_monthly")
    assert [j.dedupe_key for j in backups] == ["backup.daily:2026-10-02T01:00:00+00:00"]
    assert [j.dedupe_key for j in aum] == ["reports.aum_monthly:2026-10-01T04:00:00+00:00"]
    # And a second round of ticks for the same moment adds nothing.
    tick(now=now, app=app)
    assert len(_jobs("backup.run")) == 1 and len(_jobs("reports.aum_monthly")) == 1


def test_disabled_backup_is_never_enqueued(app):
    now = datetime(2026, 10, 2, 6, 0, tzinfo=UTC)
    _set_last_slot("backup.daily", now - timedelta(days=3))
    tick(now=now, app=app)
    assert _jobs("backup.run") == []
    assert db.session.get(PeriodicTask, "backup.daily").next_slot is None


# ── Catch-up after downtime ──


def test_catch_up_runs_each_missed_month_but_only_the_latest_backup(app, monkeypatch):
    monkeypatch.setitem(app.config, "DB_BACKUP_ENABLED", True)
    now = datetime(2026, 10, 2, 6, 0, tzinfo=UTC)
    _set_last_slot("reports.aum_monthly", datetime(2026, 7, 1, 4, 0, tzinfo=UTC))
    _set_last_slot("backup.daily", now - timedelta(days=3))
    tick(now=now, app=app)
    assert [j.args["slot"] for j in _jobs("reports.aum_monthly")] == [
        "2026-08-01T04:00:00+00:00", "2026-09-01T04:00:00+00:00", "2026-10-01T04:00:00+00:00"]
    assert len(_jobs("backup.run")) == 1


def test_catch_up_aum_jobs_summarise_the_months_they_were_due_for(app, superadmin, make_investor, deposit):
    superadmin.patch("/api/v1/settings/scheduled-reports", {"aum_enabled": True, "aum_recipients": "md@anchorstone.test"})
    deposit(make_investor()["id"], "1000", "2026-06-15")
    _set_last_slot("reports.aum_monthly", datetime(2026, 7, 1, 4, 0, tzinfo=UTC))
    tick(now=datetime(2026, 10, 2, 6, 0, tzinfo=UTC), app=app)
    while (job_id := queue.claim("w", ["reports"])) is not None:
        assert queue.run(job_id, "w") == "succeeded"
    subjects = [e.subject for e in OutboxEmail.query.filter_by(email_type="AUM_REPORT").order_by(OutboxEmail.id)]
    assert subjects == ["Monthly AUM summary — July 2026", "Monthly AUM summary — August 2026",
                        "Monthly AUM summary — September 2026"]


def test_slot_arithmetic():
    drain = PERIODIC_BY_NAME["email.drain"]
    last = datetime(2026, 10, 2, 6, 0, tzinfo=UTC)
    assert due_slots(drain, {"minutes": 2}, last, last + timedelta(minutes=1)) == []
    assert due_slots(drain, {"minutes": 2}, last, last + timedelta(minutes=9)) == [last + timedelta(minutes=8)]
    monthly = PERIODIC_BY_NAME["reports.aum_monthly"]
    spec = {"day": 31, "hour": 4, "minute": 0}  # short months use their last day
    assert due_slots(monthly, spec, datetime(2026, 1, 31, 4, tzinfo=UTC), datetime(2026, 3, 1, tzinfo=UTC)) == [
        datetime(2026, 2, 28, 4, tzinfo=UTC)]


# ── Restartable ──


def test_a_job_whose_worker_died_is_reclaimed_and_completed(app):
    job_id = queue.enqueue("test.count", {"n": 5})
    db.session.commit()
    assert queue.claim("dead-worker", ["test"]) == job_id
    job = db.session.get(Job, job_id)
    job.heartbeat_at = utcnow() - timedelta(hours=1)
    db.session.commit()
    assert queue.reclaim_stale() == 1
    assert db.session.get(Job, job_id).status == "queued"
    assert queue.claim("live-worker", ["test"]) == job_id
    assert queue.run(job_id, "live-worker") == "succeeded"
    job = db.session.get(Job, job_id)
    assert job.attempts == 2 and RUNS == [5] and job.status == "succeeded"


def test_a_live_job_is_not_reclaimed(app):
    queue.enqueue("test.count", {"n": 1})
    db.session.commit()
    queue.claim("w", ["test"])
    assert queue.reclaim_stale() == 0


def test_failures_retry_with_backoff_then_fail(app):
    job_id = queue.enqueue("test.boom")
    db.session.commit()
    assert queue.claim("w", ["test"]) == job_id
    assert queue.run(job_id, "w") == "queued"
    job = db.session.get(Job, job_id)
    assert job.attempts == 1 and "deliberate failure" in job.last_error and job.run_at > utcnow()
    assert queue.claim("w", ["test"]) is None  # not due yet
    assert queue.claim("w", ["test"], now=job.run_at + timedelta(seconds=1)) == job_id
    assert queue.run(job_id, "w") == "failed"
    assert db.session.get(Job, job_id).finished_at is not None


# ── The real tasks ──


def test_email_drain_job_sends_the_queue(app, make_investor, deposit):
    deposit(make_investor()["id"], "1000", "2026-09-01")
    assert OutboxEmail.query.filter_by(status=STATUS_QUEUED).count() == 1
    job_id = queue.enqueue("email.drain")
    db.session.commit()
    with mail.record_messages() as outbox:
        assert queue.run(queue.claim("w", ["email"]), "w") == "succeeded"
    assert len(outbox) == 1 and OutboxEmail.query.one().status == STATUS_SENT
    assert db.session.get(Job, job_id).result == {"claimed": 1, "sent": 1, "failed": 0}


def test_emails_stuck_in_sending_are_requeued(app, make_investor, deposit):
    deposit(make_investor()["id"], "1000", "2026-09-01")
    email = OutboxEmail.query.one()
    email.status = STATUS_SENDING
    db.session.commit()
    queue.enqueue("email.recover_stuck")
    db.session.commit()
    queue.run(queue.claim("w", ["email"]), "w")
    assert db.session.get(OutboxEmail, email.id).status == STATUS_SENDING  # recent: may still be sending
    db.session.execute(db.text("UPDATE email_outbox SET date_updated = now() - interval '1 hour'"))
    queue.enqueue("email.recover_stuck")
    db.session.commit()
    queue.run(queue.claim("w", ["email"]), "w")
    assert db.session.get(OutboxEmail, email.id).status == STATUS_QUEUED


def test_backup_run_now_is_queued_for_the_worker(superadmin, admin1):
    assert admin1.post("/api/v1/backups/run-now").status_code == 403
    res = superadmin.post("/api/v1/backups/run-now")
    assert res.status_code == 202
    job = db.session.get(Job, res.get_json()["data"]["job_id"])
    assert job.name == "backup.run" and job.args["triggered_by"] == "manual" and job.queue == "backup"
    assert superadmin.post("/api/v1/backups/run-now").status_code == 409  # one at a time


def test_failed_backup_marks_the_job_failed(app, monkeypatch, superadmin):
    from app.Backup.model import BackupLog
    from app.utils.backup_service import BackupService

    def fake(app_, triggered_by, user_email=None):
        log = BackupLog(filename="x.dump", status="failed", triggered_by=triggered_by, error_message="no pg_dump",
                        started_at=utcnow())
        db.session.add(log)
        db.session.commit()
        return log

    monkeypatch.setattr(BackupService, "run_database_backup", staticmethod(fake))
    job_id = superadmin.post("/api/v1/backups/run-now").get_json()["data"]["job_id"]
    assert queue.run(queue.claim("w", ["backup"]), "w") == "failed"
    assert "no pg_dump" in db.session.get(Job, job_id).last_error


def test_screens_still_show_the_next_run(app, staff, superadmin):
    tick(app=app)
    assert staff.get("/api/v1/emails/status").get_json()["data"]["next_run_at"] is not None
    assert superadmin.get("/api/v1/settings/email-queue").get_json()["data"]["next_run_at"] is not None
    assert superadmin.get("/api/v1/backups/status").get_json()["data"]["next_run_at"] is None  # backups off


def test_worker_command_is_registered(app):
    assert "worker" in app.cli.commands
