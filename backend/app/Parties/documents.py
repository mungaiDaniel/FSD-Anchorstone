"""
A client's documents (FSD v0.1 §5.1, and the image capture rows of the onboarding
list). Files go through app/Documents/service.py only: encrypted at rest, every
read logged, never deleted (destroying one is a document.destroy change request).

A new upload of the same type doesn't replace the old file: the older one is kept
and listed as an earlier version.
"""
from app.Documents import service as store
from app.Documents.model import Document, DocumentLink
from app.Parties import service as parties
from app.utils.http import Conflict, ValidationError

# FSD v0.1 §5.1 (the documents the pipeline will read) and the CRB report (phase 3a), plus photo, signature and the
# signed consent form from the onboarding image list, and "other".
PARTY_DOCUMENT_TYPES = ("national_id", "passport", "kra_pin", "cr12", "certificate_of_incorporation", "bank_statement",
                        "mpesa_statement", "audited_financial_statements", "title_deed", "logbook", "valuation_report",
                        "crb_report", "photo", "signature", "consent_form", "other")
DOCUMENT_TYPE_LABELS = {
    "national_id": "National ID", "passport": "Passport", "kra_pin": "KRA PIN certificate", "cr12": "CR12",
    "certificate_of_incorporation": "Certificate of incorporation / business registration",
    "bank_statement": "Bank statement", "mpesa_statement": "M-Pesa statement",
    "audited_financial_statements": "Audited financial statements", "title_deed": "Title deed",
    "logbook": "Logbook", "valuation_report": "Valuation report", "crb_report": "CRB report", "photo": "Photo", "signature": "Signature",
    "consent_form": "Signed consent form", "other": "Other",
}


def upload_for_party(party_id: int, data: bytes, *, filename: str, content_type: str, document_type: str, actor):
    party = parties.get_party(party_id)
    if party.status == "merged":
        raise Conflict("This client was merged into another record.")
    if document_type not in PARTY_DOCUMENT_TYPES:
        raise ValidationError(f"document_type must be one of: {', '.join(PARTY_DOCUMENT_TYPES)}.")
    # Identity scans and statements are personal data: always sensitive.
    return store.upload(data, filename=filename, content_type=content_type, document_type=document_type, actor=actor,
                        sensitive=True, entity_type="party", entity_id=str(party.id), purpose=document_type)


def for_party(party_id: int) -> list[dict]:
    """Newest first; within a type, the newest active file is current and older ones are earlier versions."""
    rows = (Document.query.join(DocumentLink, DocumentLink.document_id == Document.id)
            .filter(DocumentLink.entity_type == "party", DocumentLink.entity_id == str(party_id))
            .order_by(Document.uploaded_at.desc(), Document.id).all())
    seen, out = set(), []
    for doc in rows:
        current = doc.status == "active" and (doc.document_type == "other" or doc.document_type not in seen)
        if doc.status == "active":
            seen.add(doc.document_type)
        out.append({**doc.to_dict(), "label": DOCUMENT_TYPE_LABELS.get(doc.document_type, doc.document_type),
                    "current": current})
    return out
