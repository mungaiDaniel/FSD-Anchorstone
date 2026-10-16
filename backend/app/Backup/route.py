from flask import Blueprint, current_app, request

from app.auth import actor_email, requires
from app.Backup.model import BackupLog
from app.database.database import db
from app.Jobs.model import Job
from app.Jobs.queue import enqueue
from app.Jobs.scheduler import next_run
from app.utils.audit_log import create_audit_log
from app.utils.http import Conflict, ok

backup_v1 = Blueprint("backup_v1", __name__)


@backup_v1.get("/api/v1/backups")
@requires("backup.view")
def list_backups():
    limit = min(max(request.args.get("limit", default=50, type=int) or 50, 1), 200)
    rows = db.session.query(BackupLog).order_by(BackupLog.started_at.desc()).limit(limit).all()
    return ok([r.to_dict() for r in rows])


@backup_v1.get("/api/v1/backups/status")
@requires("backup.view")
def backup_status():
    last = db.session.query(BackupLog).order_by(BackupLog.started_at.desc()).first()
    return ok({
        "enabled": bool(current_app.config.get("DB_BACKUP_ENABLED")),
        "next_run_at": next_run("backup.daily"),
        "last_backup": last.to_dict() if last else None,
    })


@backup_v1.post("/api/v1/backups/run-now")
@requires("backup.run")
def run_backup_now():
    """Queue a backup for the worker. pg_dump can take far longer than an HTTP request may."""
    if db.session.query(Job.id).filter(Job.name == "backup.run", Job.status.in_(("queued", "running"))).first():
        raise Conflict("A backup is already queued or running.")
    job_id = enqueue("backup.run", {"triggered_by": "manual", "user_email": actor_email()},
                     priority=10, enqueued_by=actor_email())
    create_audit_log("START_BACKUP", target_type="job", target_id=job_id, description="Manual backup queued")
    db.session.commit()
    return ok({"job_id": job_id}, "Backup started. It appears in the list when it finishes.", 202)
