"""
The one background scheduler: drains the email outbox on an interval and,
when enabled, runs the daily database backup.
"""
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)

EMAIL_JOB_ID = "email_queue_drain"
BACKUP_JOB_ID = "daily_db_backup"
AUM_REPORT_JOB_ID = "monthly_aum_report"

scheduler: BackgroundScheduler | None = None


def _drain_job(app):
    from app.Emails.sender import drain_queue
    from app.Settings.service import get_effective_email_settings
    from app.database.database import db

    with app.app_context():
        try:
            batch_size = int(get_effective_email_settings(app, db.session).get("email_queue_batch_size") or 100)
            drain_queue(batch_size)
        except Exception:
            logger.error("Email queue drain failed", exc_info=True)
            db.session.rollback()


def _backup_job(app):
    from app.utils.backup_service import BackupService

    with app.app_context():
        log = BackupService.run_database_backup(app, triggered_by="scheduled")
        if log.status != "success":
            logger.error("Scheduled backup failed: %s", log.error_message)


def _aum_report_job(app):
    from app.database.database import db
    from app.Reports.scheduled import scheduled_run

    with app.app_context():
        try:
            n = scheduled_run()
            if n:
                logger.info("Monthly AUM summary generated for %s recipient(s), awaiting confirmation", n)
        except Exception:
            logger.error("Monthly AUM summary failed", exc_info=True)
            db.session.rollback()


def start_scheduler(app) -> None:
    global scheduler
    if scheduler is not None:
        return
    from app.database.database import db
    from app.Emails.sender import recover_stuck_sending
    from app.Settings.service import get_effective_email_settings

    with app.app_context():
        recovered = recover_stuck_sending()
        if recovered:
            logger.warning("Re-queued %s email(s) left in 'sending' by a previous run", recovered)
        interval = int(get_effective_email_settings(app, db.session).get("email_queue_interval_minutes") or 2)

    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(_drain_job, IntervalTrigger(minutes=interval), args=[app], id=EMAIL_JOB_ID,
                      name="Send queued investor emails", replace_existing=True, coalesce=True, max_instances=1)
    # 1st of each month, 07:00 Nairobi time (04:00 UTC). The job itself checks whether
    # the schedule is switched on, so turning it on/off in Settings needs no restart.
    scheduler.add_job(_aum_report_job, CronTrigger(day=1, hour=4, minute=0, timezone="UTC"), args=[app],
                      id=AUM_REPORT_JOB_ID, name="Monthly AUM summary", replace_existing=True,
                      coalesce=True, max_instances=1, misfire_grace_time=6 * 3600)
    if app.config.get("DB_BACKUP_ENABLED"):
        scheduler.add_job(_backup_job,
                          CronTrigger(hour=app.config["DB_BACKUP_HOUR_UTC"], minute=app.config["DB_BACKUP_MINUTE_UTC"]),
                          args=[app], id=BACKUP_JOB_ID, name="Daily database backup",
                          replace_existing=True, coalesce=True, max_instances=1)
    scheduler.start()
    logger.info("Scheduler started: email queue every %s min, backups %s",
                interval, "on" if app.config.get("DB_BACKUP_ENABLED") else "off")


def reschedule_email_queue(interval_minutes: int) -> None:
    if scheduler is not None:
        scheduler.reschedule_job(EMAIL_JOB_ID, trigger=IntervalTrigger(minutes=interval_minutes))


def next_run(job_id: str) -> str | None:
    if scheduler is None:
        return None
    job = scheduler.get_job(job_id)
    return job.next_run_time.isoformat() if job and job.next_run_time else None
