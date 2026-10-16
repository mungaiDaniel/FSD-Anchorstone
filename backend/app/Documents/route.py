"""
Document storage API (no screen yet; phase 2b adds KYC upload screens).

    POST /api/v1/documents                    multipart: file, document_type, sensitive, entity_type, entity_id
    GET  /api/v1/documents/<id>               metadata (logged as a view)
    GET  /api/v1/documents/<id>/content       the decrypted file (logged as a download)
    POST /api/v1/documents/<id>/destroy       {reason} → a change request for a second person
"""
import io

from flask import Blueprint, request, send_file

from app.Approvals import service as approvals
from app.auth import current_user, requires
from app.Documents import service
from app.utils.http import ValidationError, ok

documents_v1 = Blueprint("documents_v1", __name__)


@documents_v1.post("/api/v1/documents")
@requires("document.upload")
def upload_document():
    file = request.files.get("file")
    if file is None:
        raise ValidationError("Attach the file as 'file'.")
    form = request.form
    doc = service.upload(
        file.read(), filename=file.filename, content_type=file.mimetype, document_type=form.get("document_type") or "",
        actor=current_user(), sensitive=(form.get("sensitive", "true").lower() != "false"),
        entity_type=form.get("entity_type") or None, entity_id=form.get("entity_id") or None,
        purpose=form.get("purpose") or "kyc",
    )
    return ok(doc.to_dict(), "Document stored (encrypted).", 201)


@documents_v1.get("/api/v1/documents/<uuid:document_id>")
@requires("document.view")
def get_document(document_id):
    return ok(service.metadata(document_id, current_user()).to_dict())


@documents_v1.get("/api/v1/documents/<uuid:document_id>/content")
@requires("document.view")
def download_document(document_id):
    doc, data = service.read(document_id, current_user())
    response = send_file(io.BytesIO(data), mimetype=doc.content_type, as_attachment=True,
                         download_name=doc.original_filename, max_age=0)
    response.headers["Cache-Control"] = "no-store"
    return response


@documents_v1.post("/api/v1/documents/<uuid:document_id>/destroy")
@requires("document.destroy.request")
def request_destruction(document_id):
    data = request.get_json(silent=True) or {}
    cr = approvals.submit("document.destroy", {"document_id": str(document_id), "reason": data.get("reason")},
                          current_user(), data.get("reason"))
    return ok(cr.to_dict(approvals.summary(cr)), "Submitted for approval. The document is destroyed once approved.", 201)
