"""
Uploading, reading and destroying documents.

Access is only through the backend: no store URL ever reaches a browser.
Reading needs document.view, and document.view.sensitive for a sensitive
document; every read is logged in data_access_logs. Destroying a document is
a change request (document.destroy), approved by someone other than the maker.
"""
import hashlib
import uuid

from flask import has_request_context, request

from app.Access.service import permissions_for
from app.Admin.model import User
from app.Approvals.handlers import Handler, register
from app.database.database import db
from app.Documents import crypto
from app.Documents.model import DOC_ACTIVE, DOC_DESTROYED, DataAccessLog, Document, DocumentLink
from app.Documents.store import get_store
from app.Settings import business as settings
from app.utils.audit_log import create_audit_log, get_client_ip
from app.utils.dates import utcnow
from app.utils.http import ApiError, Conflict, Forbidden, NotFound, ValidationError


class Gone(ApiError):
    status_code = 410


class DocumentIntegrityError(ApiError):
    status_code = 500


DOCUMENT_TYPES = ("national_id", "passport", "kra_pin", "cr12", "certificate_of_incorporation", "bank_statement",
                  "mpesa_statement", "audited_financial_statements", "title_deed", "logbook", "valuation_report",
                  "payslip", "photo", "signature", "consent_form", "other")

# First bytes of each accepted type: the declared content type must match the file.
_MAGIC = {
    "application/pdf": (b"%PDF-",),
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/tiff": (b"II*\x00", b"MM\x00*"),
}


def _looks_like(content_type: str, data: bytes) -> bool:
    if content_type == "image/heic":
        return data[4:8] == b"ftyp" and data[8:12] in (b"heic", b"heix", b"mif1", b"msf1", b"heim", b"heis")
    return any(data.startswith(m) for m in _MAGIC.get(content_type, ()))


def _log_access(document: Document | None, actor: User, action: str, entity=(None, None)) -> None:
    db.session.add(DataAccessLog(
        user_id=actor.id if actor else None, user_email=actor.email if actor else "system",
        document_id=document.id if document else None, entity_type=entity[0], entity_id=entity[1], action=action,
        ip_address=get_client_ip() if has_request_context() else None,
        user_agent=(request.headers.get("User-Agent") or "")[:255] if has_request_context() else None,
        at=utcnow()))


def upload(data: bytes, *, filename: str, content_type: str, document_type: str, actor: User,
           sensitive: bool = True, entity_type: str | None = None, entity_id: str | None = None,
           purpose: str = "kyc") -> Document:
    kek = crypto.current_kek()
    if document_type not in DOCUMENT_TYPES:
        raise ValidationError(f"document_type must be one of: {', '.join(DOCUMENT_TYPES)}.")
    content_type = (content_type or "").split(";")[0].strip().lower()
    if content_type not in settings.get("documents.allowed_types"):
        raise ValidationError("This file type isn't accepted. Upload a PDF, JPEG, PNG, HEIC or TIFF file.")
    max_mb = settings.get("documents.max_mb")
    if not data:
        raise ValidationError("The file is empty.")
    if len(data) > max_mb * 1024 * 1024:
        raise ValidationError(f"The file is larger than {max_mb} MB.")
    if not _looks_like(content_type, data):
        raise ValidationError(f"The file's contents don't match its type ({content_type}).")
    if (entity_type is None) != (entity_id is None):
        raise ValidationError("Give both entity_type and entity_id, or neither.")

    doc_id = uuid.uuid4()
    sealed = crypto.seal(data, doc_id.bytes, kek)
    now = utcnow()
    store = get_store()
    doc = Document(
        id=doc_id, storage_backend=store.name, storage_key=f"documents/{now:%Y}/{now:%m}/{doc_id}",
        document_type=document_type, original_filename=(filename or "document")[:255], content_type=content_type,
        size_bytes=len(data), sha256=hashlib.sha256(data).hexdigest(), wrapped_data_key=sealed.wrapped_key,
        key_id=sealed.key_id, nonce=sealed.nonce, sensitive=sensitive, status=DOC_ACTIVE,
        uploaded_by=actor.email, uploaded_at=now,
    )
    db.session.add(doc)
    db.session.flush()  # the row must exist before its link and access log
    if entity_type:
        db.session.add(DocumentLink(document_id=doc_id, entity_type=entity_type, entity_id=str(entity_id),
                                    purpose=purpose, linked_by=actor.email))
    _log_access(doc, actor, "upload", (entity_type, entity_id))
    db.session.flush()
    create_audit_log("UPLOAD_DOCUMENT", target_type="document", target_name=str(doc_id),
                     description=f"{document_type}, {len(data)} bytes", new_value={"document_type": document_type,
                     "content_type": content_type, "size_bytes": len(data), "sensitive": sensitive})
    store.put(doc.storage_key, sealed.ciphertext)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        store.delete(doc.storage_key)
        raise
    return doc


def get_document(document_id) -> Document:
    doc = db.session.get(Document, document_id)
    if doc is None:
        raise NotFound("Document not found.")
    return doc


def _assert_can_view(doc: Document, actor: User) -> None:
    held = permissions_for(actor)
    if "document.view" not in held or (doc.sensitive and "document.view.sensitive" not in held):
        raise Forbidden("You do not have permission to open this document.")


def read(document_id, actor: User, action: str = "download") -> tuple[Document, bytes]:
    doc = get_document(document_id)
    _assert_can_view(doc, actor)
    if doc.status == DOC_DESTROYED:
        raise Gone("This document was destroyed and can't be opened.")
    try:
        data_key = crypto.unwrap(doc.wrapped_data_key, doc.id.bytes, crypto.kek_for(doc.key_id))
        plaintext = crypto.open_sealed(get_store().get(doc.storage_key), doc.nonce, data_key, doc.id.bytes)
        if hashlib.sha256(plaintext).hexdigest() != doc.sha256:
            raise crypto.IntegrityFailure("Checksum mismatch.")
    except (crypto.IntegrityFailure, FileNotFoundError) as e:
        db.session.rollback()
        create_audit_log("DOCUMENT_INTEGRITY_FAILURE", target_type="document", target_name=str(doc.id),
                         description=str(e), success=False, error_message=str(e))
        db.session.commit()
        raise DocumentIntegrityError("This document failed its integrity check and wasn't served. It has been reported.")
    _log_access(doc, actor, action)
    db.session.commit()
    return doc, plaintext


def metadata(document_id, actor: User) -> Document:
    doc = get_document(document_id)
    _assert_can_view(doc, actor)
    _log_access(doc, actor, "view")
    db.session.commit()
    return doc


@register
class DestroyDocument(Handler):
    """payload = {document_id, reason}. Crypto-shreds: the data key goes, then the blob."""

    request_type = "document.destroy"
    entity_type = "document"
    submit_permission = "document.destroy.request"

    def entity_id(self, payload):
        return payload["document_id"]

    def validate(self, payload):
        try:
            doc_id = uuid.UUID(str(payload.get("document_id")))
        except ValueError:
            raise ValidationError("document_id must be a document id.")
        reason = (payload.get("reason") or "").strip()
        if not reason:
            raise ValidationError("A reason is required to destroy a document.")
        doc = get_document(doc_id)
        if doc.status == DOC_DESTROYED:
            raise ValidationError("This document has already been destroyed.")
        if doc.legal_hold:
            raise ValidationError("This document is under legal hold and can't be destroyed.")
        return {"document_id": str(doc_id), "reason": reason}

    def base_version(self, payload):
        doc = db.session.get(Document, uuid.UUID(payload["document_id"]))
        return f"{doc.status}:{doc.legal_hold}" if doc else None

    def describe(self, payload):
        return f"Destroy document {payload['document_id']}: {payload['reason']}"

    def apply(self, request, actor):
        doc = (db.session.query(Document).filter(Document.id == uuid.UUID(request.payload["document_id"]))
               .with_for_update().one())
        if doc.status == DOC_DESTROYED:
            raise Conflict("This document has already been destroyed.")
        doc.wrapped_data_key = None
        doc.status = DOC_DESTROYED
        doc.destroyed_by = actor.email
        doc.destroyed_at = utcnow()
        doc.destroy_reason = request.payload["reason"]
        _log_access(doc, actor, "destroy")
        db.session.flush()
        get_store().delete(doc.storage_key)
        return {"document_id": str(doc.id), "status": doc.status}
