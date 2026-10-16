"""
The worker process:  flask --app main worker [--queues email,reports] [--poll 2]

Loop: every TICK_SECONDS, enqueue due periodic jobs and reclaim jobs from dead
workers; otherwise claim the next due job and run it. One job at a time per
process; run more processes (they never run the same job twice) for more
throughput. SIGTERM / Ctrl+C finishes the current job, then exits.

A heartbeat file (WORKER_HEARTBEAT_FILE) is touched every loop so a container
health check can tell the worker is alive.
"""
import logging
import os
import pathlib
import signal
import socket
import threading
import time
import uuid

from app.database.database import db
from app.Jobs.queue import claim, reclaim_stale, run
from app.Jobs.scheduler import tick

logger = logging.getLogger("anchorstone.worker")

TICK_SECONDS = 15


def worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:6]}"


def run_worker(app, queues: list[str] | None = None, poll_seconds: float = 2.0,
               stop: threading.Event | None = None, max_jobs: int | None = None) -> int:
    stop = stop or threading.Event()
    me = worker_id()
    heartbeat = pathlib.Path(app.config.get("WORKER_HEARTBEAT_FILE") or "")
    done = 0
    last_tick = 0.0

    def _stop(signum, frame):
        logger.info("Worker %s stopping after the current job", me)
        stop.set()

    if threading.current_thread() is threading.main_thread():
        signal.signal(signal.SIGINT, _stop)
        signal.signal(signal.SIGTERM, _stop)

    logger.info("Worker %s started (queues: %s)", me, ", ".join(queues) if queues else "all")
    while not stop.is_set():
        with app.app_context():
            try:
                if time.monotonic() - last_tick >= TICK_SECONDS:
                    tick(app=app)
                    reclaim_stale()
                    last_tick = time.monotonic()
                job_id = claim(me, queues)
                if job_id is not None:
                    status = run(job_id, me, app)
                    logger.info("Job %s finished: %s", job_id, status)
                    done += 1
            except Exception:
                logger.error("Worker loop error", exc_info=True)
                db.session.rollback()
                job_id = None
            finally:
                db.session.remove()
        if heartbeat.name:
            try:
                heartbeat.touch()
            except OSError:
                pass
        if max_jobs is not None and done >= max_jobs:
            break
        if job_id is None:
            stop.wait(poll_seconds)
    logger.info("Worker %s stopped after %s job(s)", me, done)
    return done
