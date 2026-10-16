from datetime import datetime, timezone

from sqlalchemy import Column, DateTime
from sqlalchemy.orm import declarative_base


def _utcnow():
    return datetime.now(timezone.utc)


class BaseModel(object):
    """Row timestamps shared by every table."""

    __abstract__ = True

    date_created = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    date_updated = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


Base = declarative_base(cls=BaseModel)
