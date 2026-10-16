from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, BigInteger, Text, Boolean
from base_model import Base
from app.database.database import db


class BackupLog(Base, db.Model):
    """
    Insert-only audit trail of database backup attempts (scheduled or manual).

    One row per pg_dump -> OneDrive upload attempt. `status` moves
    running -> success | failed. Rows are never deleted (retention = keep all),
    even after the remote copy is eventually cleaned up by hand.
    """
    __tablename__ = "backup_logs"

    id = Column(Integer, primary_key=True)
    filename = Column(String(255), nullable=False)
    status = Column(String(20), nullable=False, default="running")  # running | success | failed
    triggered_by = Column(String(20), nullable=False, default="scheduled")  # scheduled | manual
    triggered_by_email = Column(String(120), nullable=True)
    file_size_bytes = Column(BigInteger, nullable=True)
    onedrive_item_id = Column(String(255), nullable=True)
    onedrive_web_url = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime(timezone=True), nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "filename": self.filename,
            "status": self.status,
            "triggered_by": self.triggered_by,
            "triggered_by_email": self.triggered_by_email,
            "file_size_bytes": self.file_size_bytes,
            "onedrive_web_url": self.onedrive_web_url,
            "error_message": self.error_message,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
