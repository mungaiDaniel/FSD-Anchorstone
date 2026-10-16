"""
Database backup service: pg_dump the app database, upload the dump to
OneDrive, and record the attempt in backup_logs.

Triggered either by BackupSchedulerService (daily, APScheduler) or by a
super-admin clicking "Run backup now" on the Backups page.
"""
import logging
import os
import subprocess
import tempfile
from datetime import datetime, timezone

from sqlalchemy.engine import make_url

from app.database.database import db
from app.Backup.model import BackupLog
from app.utils.onedrive_client import OneDriveClient, OneDriveConfigError

logger = logging.getLogger(__name__)


class BackupService:

    @staticmethod
    def run_database_backup(app, triggered_by: str = "scheduled", user_email: str | None = None) -> BackupLog:
        """
        Runs pg_dump against app.config['SQLALCHEMY_DATABASE_URI'], uploads the
        resulting dump to OneDrive, and returns the completed BackupLog row.

        Always creates a BackupLog row, even on failure, so every attempt is
        auditable. Never raises for expected failure modes (missing config,
        pg_dump error, upload error) — the error is recorded on the row instead;
        callers should check `log.status`.
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"anchorstone_backup_{timestamp}.dump"

        log = BackupLog(
            filename=filename,
            status="running",
            triggered_by=triggered_by,
            triggered_by_email=user_email,
        )
        db.session.add(log)
        db.session.commit()

        tmp_path = None
        try:
            tmp_dir = tempfile.mkdtemp(prefix="anchorstone_backup_")
            tmp_path = os.path.join(tmp_dir, filename)

            BackupService._run_pg_dump(app, tmp_path)
            file_size = os.path.getsize(tmp_path)

            client = OneDriveClient(app)
            item = client.upload_file(tmp_path, filename)

            log.status = "success"
            log.file_size_bytes = file_size
            log.onedrive_item_id = item.get("id")
            log.onedrive_web_url = item.get("webUrl")
            log.completed_at = datetime.now(timezone.utc)
            db.session.commit()
            logger.info(f"Backup succeeded: {filename} ({file_size} bytes)")

        except OneDriveConfigError as e:
            log.status = "failed"
            log.error_message = str(e)
            log.completed_at = datetime.now(timezone.utc)
            db.session.commit()
            logger.error(f"Backup failed (config): {e}")

        except Exception as e:
            log.status = "failed"
            log.error_message = str(e)
            log.completed_at = datetime.now(timezone.utc)
            db.session.commit()
            logger.error(f"Backup failed: {e}", exc_info=True)

        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                    os.rmdir(os.path.dirname(tmp_path))
                except OSError:
                    pass

        return log

    @staticmethod
    def _run_pg_dump(app, output_path: str) -> None:
        uri = app.config.get("SQLALCHEMY_DATABASE_URI")
        if not uri:
            raise RuntimeError("SQLALCHEMY_DATABASE_URI is not configured")

        url = make_url(uri)
        pg_dump_path = app.config.get("PG_DUMP_PATH") or "pg_dump"

        cmd = [
            pg_dump_path,
            "-h", url.host or "localhost",
            "-p", str(url.port or 5432),
            "-U", url.username or "postgres",
            "-Fc",  # custom format: compressed, restorable with pg_restore
            "-f", output_path,
            url.database,
        ]

        env = os.environ.copy()
        if url.password:
            env["PGPASSWORD"] = url.password

        result = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=1800)
        if result.returncode != 0:
            raise RuntimeError(f"pg_dump failed (exit {result.returncode}): {result.stderr.strip()}")
