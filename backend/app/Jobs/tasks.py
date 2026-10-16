"""
The background tasks. Each runs inside the worker's app context; whatever it
leaves uncommitted is committed when it returns, and rolled back if it raises.
"""
import logging
from datetime import datetime, timedelta

from flask import current_app

from app.database.database import db
from app.Jobs.registry import task
from app.utils.dates import utcnow

logger = logging.getLogger(__name__)

STUCK_SENDING_AFTER = timedelta(minutes=15)


@task("email.drain", queue="email", timeout_seconds=900)
def email_drain(args: dict):
    from app.Emails.sender import drain_queue
    from app.Settings.service import apply_email_settings_to_app, get_effective_email_settings

    app = current_app._get_current_object()
    # SMTP settings may have been changed in the web app since the last run.
    apply_email_settings_to_app(app, db.session)
    batch_size = int(args.get("batch_size") or get_effective_email_settings(app, db.session)
                     .get("email_queue_batch_size") or 100)
    return drain_queue(batch_size)


@task("email.recover_stuck", queue="email")
def email_recover_stuck(args: dict):
    """An email left 'sending' by a worker that died goes back to the queue."""
    from app.Emails.model import STATUS_QUEUED, STATUS_SENDING, OutboxEmail

    cutoff = utcnow() - STUCK_SENDING_AFTER
    count = (db.session.query(OutboxEmail)
             .filter(OutboxEmail.status == STATUS_SENDING, OutboxEmail.date_updated < cutoff)
             .update({"status": STATUS_QUEUED}, synchronize_session=False))
    if count:
        logger.warning("Re-queued %s email(s) stuck in 'sending'", count)
    return {"requeued": count}


@task("reports.aum_monthly", queue="reports")
def reports_aum_monthly(args: dict):
    from app.Reports.scheduled import scheduled_run
    from app.utils.dates import EAT

    # The slot (1st of the month, 04:00 UTC) decides which month is summarised,
    # so a catch-up run after downtime summarises the month it was due for.
    slot = datetime.fromisoformat(args["slot"]) if args.get("slot") else None
    today = slot.astimezone(EAT).date() if slot else None
    return {"generated": scheduled_run(today)}


@task("backup.run", queue="backup", max_attempts=1, timeout_seconds=2 * 3600)
def backup_run(args: dict):
    from app.utils.backup_service import BackupService

    log = BackupService.run_database_backup(current_app._get_current_object(),
                                            triggered_by=args.get("triggered_by") or "scheduled",
                                            user_email=args.get("user_email"))
    if log.status != "success":
        raise RuntimeError(f"Backup failed: {log.error_message}")
    return {"backup_log_id": log.id, "status": log.status}


@task("change_requests.expire", queue="default")
def change_requests_expire(args: dict):
    from app.Approvals.service import expire_due
    return {"expired": expire_due()}


@task("screening.rescreen", queue="default", timeout_seconds=3600)
def screening_rescreen(args: dict):
    """Re-screen every active client against the watchlists (FSD KYC-06: new and existing clients)."""
    from app.Parties.screening import rescreen_all
    return rescreen_all("scheduler")


@task("screening.un_sanctions_import", queue="default", timeout_seconds=1800)
def screening_un_sanctions_import(args: dict):
    """Refresh the UN Security Council sanctions list (FSD KYC-06), when the import is switched on."""
    from app.Parties.sanctions_un import scheduled_import
    return scheduled_import("scheduler")


@task("test.noop", queue="default")
def noop(args: dict):
    """Does nothing; used to check a worker is alive (and by tests)."""
    return {"ok": True, "echo": args.get("echo")}
