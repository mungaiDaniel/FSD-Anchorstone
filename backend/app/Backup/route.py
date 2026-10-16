from flask import Blueprint, current_app, request

from app.auth import actor_email, requires
from app.Backup.model import BackupLog
from app.database.database import db
from app.logic.scheduler import BACKUP_JOB_ID, next_run
from app.utils.backup_service import BackupService
from app.utils.http import error, ok

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
        "next_run_at": next_run(BACKUP_JOB_ID),
        "last_backup": last.to_dict() if last else None,
    })


@backup_v1.post("/api/v1/backups/run-now")
@requires("backup.run")
def run_backup_now():
    log = BackupService.run_database_backup(current_app._get_current_object(), triggered_by="manual",
                                            user_email=actor_email())
    if log.status != "success":
        return error(log.error_message or "Backup failed", 500)
    return ok(log.to_dict(), "Backup completed.")
