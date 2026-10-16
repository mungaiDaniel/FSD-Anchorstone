"""
Documents: metadata in PostgreSQL, encrypted bytes in a DocumentStore.

A document row is never deleted. Destroying it (a change request) erases its
wrapped data key and its blob and sets status 'destroyed'; the database
refuses DELETE and any change to a destroyed row. Every view, download,
upload and destruction writes an insert-only data_access_logs row.
"""
import uuid

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID

from app.database.database import db
from app.utils.dates import iso
from base_model import Base

DOC_ACTIVE = "active"
DOC_DESTROYED = "destroyed"
ACCESS_ACTIONS = ("view", "download", "upload", "destroy")


class Document(Base, db.Model):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'destroyed')", name="ck_documents_status"),
        CheckConstraint("(status = 'destroyed') = (wrapped_data_key IS NULL)", name="ck_documents_key_iff_active"),
        CheckConstraint("size_bytes >= 0", name="ck_documents_size"),
        CheckConstraint("char_length(sha256) = 64", name="ck_documents_sha256"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    storage_backend = Column(String(20), nullable=False)
    storage_key = Column(String(200), nullable=False, unique=True)
    document_type = Column(String(50), nullable=False)
    original_filename = Column(String(255), nullable=False)
    content_type = Column(String(100), nullable=False)
    size_bytes = Column(BigInteger, nullable=False)
    sha256 = Column(String(64), nullable=False)  # of the plaintext, checked on every read
    wrapped_data_key = Column(LargeBinary, nullable=True)  # NULL once destroyed
    key_id = Column(String(50), nullable=False)
    nonce = Column(LargeBinary, nullable=False)
    sensitive = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    status = Column(String(10), nullable=False, default=DOC_ACTIVE, server_default=DOC_ACTIVE)
    retention_until = Column(Date, nullable=True)
    legal_hold = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    uploaded_by = Column(String(120), nullable=False)
    uploaded_at = Column(DateTime(timezone=True), nullable=False)
    destroyed_by = Column(String(120), nullable=True)
    destroyed_at = Column(DateTime(timezone=True), nullable=True)
    destroy_reason = Column(Text, nullable=True)

    def to_dict(self) -> dict:
        return {"id": str(self.id), "document_type": self.document_type, "filename": self.original_filename,
                "content_type": self.content_type, "size_bytes": self.size_bytes, "sha256": self.sha256,
                "sensitive": self.sensitive, "status": self.status, "legal_hold": self.legal_hold,
                "retention_until": iso(self.retention_until), "uploaded_by": self.uploaded_by,
                "uploaded_at": iso(self.uploaded_at), "destroyed_by": self.destroyed_by,
                "destroyed_at": iso(self.destroyed_at), "destroy_reason": self.destroy_reason,
                "links": [link.to_dict() for link in DocumentLink.query.filter_by(document_id=self.id)]}


class DocumentLink(Base, db.Model):
    """One scan can serve several records (a party's KYC, an application, a collateral item)."""

    __tablename__ = "document_links"
    __table_args__ = (UniqueConstraint("document_id", "entity_type", "entity_id", "purpose",
                                       name="uq_document_links"),
                      Index("ix_document_links_entity", "entity_type", "entity_id"))

    id = Column(Integer, primary_key=True)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="RESTRICT"), nullable=False)
    entity_type = Column(String(50), nullable=False)
    entity_id = Column(String(64), nullable=False)
    purpose = Column(String(50), nullable=False, default="kyc", server_default="kyc")
    linked_by = Column(String(120), nullable=False)

    def to_dict(self) -> dict:
        return {"entity_type": self.entity_type, "entity_id": self.entity_id, "purpose": self.purpose}


class DataAccessLog(Base, db.Model):
    """Who opened which personal data, when. Insert-only (database trigger)."""

    __tablename__ = "data_access_logs"
    __table_args__ = (
        CheckConstraint("action IN ('view', 'download', 'upload', 'destroy')", name="ck_data_access_logs_action"),
        Index("ix_data_access_logs_document", "document_id", "at"),
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id", ondelete="RESTRICT"), nullable=True)
    user_email = Column(String(120), nullable=False)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="RESTRICT"), nullable=True)
    entity_type = Column(String(50), nullable=True)
    entity_id = Column(String(64), nullable=True)
    action = Column(String(10), nullable=False)
    out_of_portfolio = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    ip_address = Column(String(64), nullable=True)
    user_agent = Column(String(255), nullable=True)
    at = Column(DateTime(timezone=True), nullable=False)
