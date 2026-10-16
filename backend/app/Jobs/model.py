"""
PostgreSQL-backed job queue (ADR-04-3).

    jobs            one row per unit of work; workers claim rows with
                    FOR UPDATE SKIP LOCKED, so a job is run by one worker only
    periodic_tasks  scheduler state per periodic task (the last slot enqueued);
                    the schedule itself is code (app/Jobs/registry.py)

A periodic job's dedupe_key is "<task>:<slot>", and (name, dedupe_key) is
unique, so however many worker processes tick the scheduler, each slot is
enqueued once.
"""
from sqlalchemy import CheckConstraint, Column, DateTime, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB

from app.database.database import db
from app.utils.dates import iso
from base_model import Base

JOB_QUEUED = "queued"
JOB_RUNNING = "running"
JOB_SUCCEEDED = "succeeded"
JOB_FAILED = "failed"
JOB_CANCELLED = "cancelled"
JOB_STATUSES = (JOB_QUEUED, JOB_RUNNING, JOB_SUCCEEDED, JOB_FAILED, JOB_CANCELLED)


class Job(Base, db.Model):
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint("status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')", name="ck_jobs_status"),
        CheckConstraint("max_attempts >= 1", name="ck_jobs_max_attempts"),
        Index("uq_jobs_name_dedupe_key", "name", "dedupe_key", unique=True,
              postgresql_where=text("dedupe_key IS NOT NULL")),
        Index("ix_jobs_claim", "status", "queue", "priority", "run_at"),
    )

    id = Column(Integer, primary_key=True)
    name = Column(String(60), nullable=False)
    queue = Column(String(20), nullable=False)
    args = Column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    status = Column(String(10), nullable=False, default=JOB_QUEUED, server_default=JOB_QUEUED)
    priority = Column(Integer, nullable=False, default=0, server_default="0")  # higher runs first
    run_at = Column(DateTime(timezone=True), nullable=False)
    attempts = Column(Integer, nullable=False, default=0, server_default="0")
    max_attempts = Column(Integer, nullable=False, default=3, server_default="3")
    dedupe_key = Column(String(120), nullable=True)
    enqueued_by = Column(String(120), nullable=False)
    locked_by = Column(String(120), nullable=True)
    locked_at = Column(DateTime(timezone=True), nullable=True)
    heartbeat_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)
    result = Column(JSONB, nullable=True)

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "queue": self.queue, "args": self.args, "status": self.status,
                "priority": self.priority, "run_at": iso(self.run_at), "attempts": self.attempts,
                "max_attempts": self.max_attempts, "dedupe_key": self.dedupe_key, "enqueued_by": self.enqueued_by,
                "locked_by": self.locked_by, "heartbeat_at": iso(self.heartbeat_at),
                "finished_at": iso(self.finished_at), "last_error": self.last_error, "result": self.result}


class PeriodicTask(Base, db.Model):
    __tablename__ = "periodic_tasks"

    name = Column(String(60), primary_key=True)
    last_slot = Column(DateTime(timezone=True), nullable=False)  # newest slot already enqueued (or skipped)
    next_slot = Column(DateTime(timezone=True), nullable=True)   # for "next run" on screens
    last_ticked_at = Column(DateTime(timezone=True), nullable=True)
