"""
Client consent per purpose (Kenya DPA; FSD v0.1 AI-01; 05-ai-document-pipeline §9.1).

    record(party_id, data, actor)      purpose, date granted, method (signed form,
                                       in branch, email), evidence document; the
                                       notice version comes from consent.notice_version
    withdraw(party_id, consent_id, …)  kept on the row; consents are never deleted
    has_consent(party_id, purpose)

A signed form needs the scanned form, uploaded to the client first. Without
consent for ai_document_processing no AI job can be queued or run for the
client (app/Jobs/queue.py, a task declared with consent_purpose); staff use
manual entry instead.
"""
import uuid

from app.database.database import db
from app.Documents.model import Document, DocumentLink
from app.Parties import service as parties
from app.Parties.model import CONSENT_METHODS, CONSENT_PURPOSES, PartyConsent
from app.Settings import business
from app.utils.audit_log import create_audit_log
from app.utils.dates import parse_date, today_eat, utcnow
from app.utils.http import Conflict, NotFound, ValidationError

PURPOSE_LABELS = {"kyc_processing": "KYC processing", "ai_document_processing": "automatic document reading",
                  "credit_bureau_check": "credit bureau checks", "marketing": "marketing"}


def has_consent(party_id: int, purpose: str) -> bool:
    return db.session.query(PartyConsent.id).filter_by(party_id=party_id, purpose=purpose, status="active").first() \
        is not None


def for_party(party_id: int) -> list[PartyConsent]:
    return (PartyConsent.query.filter_by(party_id=party_id)
            .order_by(PartyConsent.status, PartyConsent.purpose, PartyConsent.captured_at.desc()).all())


def record(party_id: int, data: dict, actor: str) -> PartyConsent:
    party = parties.lock_party(party_id)
    if party.status == "merged":
        raise Conflict("This client was merged into another record.")
    purpose = str(data.get("purpose") or "").strip()
    if purpose not in CONSENT_PURPOSES:
        raise ValidationError(f"purpose must be one of: {', '.join(CONSENT_PURPOSES)}.")
    method = str(data.get("method") or "").strip()
    if method not in CONSENT_METHODS:
        raise ValidationError(f"method must be one of: {', '.join(CONSENT_METHODS)}.")
    granted_on = parse_date(data.get("granted_on"), "granted_on", required=False) or today_eat()
    if granted_on > today_eat():
        raise ValidationError("granted_on can't be in the future.")
    evidence = None
    if data.get("evidence_document_id"):
        try:
            evidence = uuid.UUID(str(data["evidence_document_id"]))
        except ValueError:
            raise ValidationError("evidence_document_id must be a document id.")
        linked = DocumentLink.query.filter_by(document_id=evidence, entity_type="party", entity_id=str(party.id)).first()
        if linked is None or db.session.get(Document, evidence) is None:
            raise ValidationError("The evidence must be a document uploaded to this client.")
    if method == "signed_form" and evidence is None:
        raise ValidationError("Upload the signed consent form to the client first, then record the consent.")
    if has_consent(party.id, purpose):
        raise Conflict(f"Consent for {PURPOSE_LABELS[purpose]} is already on file.")
    row = PartyConsent(party_id=party.id, purpose=purpose, granted_on=granted_on, method=method,
                       notice_version=str(business.get("consent.notice_version")), evidence_document_id=evidence,
                       captured_by=actor, captured_at=utcnow(), status="active")
    db.session.add(row)
    db.session.flush()
    create_audit_log("RECORD_CONSENT", target_type="party", target_id=party.id, target_name=party.party_no,
                     description=f"Consent for {PURPOSE_LABELS[purpose]} ({method.replace('_', ' ')}).",
                     new_value=row.to_dict())
    db.session.commit()
    return row


def withdraw(party_id: int, consent_id: int, data: dict, actor: str) -> PartyConsent:
    party = parties.lock_party(party_id)
    row = (db.session.query(PartyConsent).filter_by(id=consent_id, party_id=party.id).with_for_update().one_or_none())
    if row is None:
        raise NotFound("Consent not found.")
    if row.status == "withdrawn":
        raise Conflict("This consent has already been withdrawn.")
    old = row.to_dict()
    row.status, row.withdrawn_at, row.withdrawn_by = "withdrawn", utcnow(), actor
    row.withdrawal_note = (str(data.get("note") or "").strip() or None)
    create_audit_log("WITHDRAW_CONSENT", target_type="party", target_id=party.id, target_name=party.party_no,
                     description=f"Consent for {PURPOSE_LABELS[row.purpose]} withdrawn.", old_value=old,
                     new_value=row.to_dict())
    db.session.commit()
    return row
