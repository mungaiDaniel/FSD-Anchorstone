"""
Pre-screen applications (phase 3b; TEMPORARY shell until phase 5's product engine).

    create(data, actor)                     applicant, product (WA-04), amount, term, rate;
                                            the instalment ESTIMATE is computed here
    add_guarantor(app_id, party_id, actor)  guarantors count as collateral owners (AI-06)
    link_document(app_id, document_id, …)   a document of the applicant or a guarantor
    enter_crb(app_id, data, actor)          CRB status, confirmed by a second person
                                            (change request application.crb_confirm)
"""
import uuid

from sqlalchemy import or_

from app.Applications.estimate import estimate
from app.Applications.model import (
    CRB_LABELS,
    CRB_STATUSES,
    PRODUCTS,
    ApplicationCrbStatus,
    ApplicationParty,
    LoanApplication,
    application_no_seq,
)
from app.Approvals import service as approvals
from app.database.database import db
from app.DocAI.model import EXTRACTION_FINISHED, Extraction
from app.Documents.model import Document, DocumentLink
from app.Parties import service as parties
from app.utils.audit_log import create_audit_log
from app.utils.dates import parse_date, today_eat, utcnow
from app.utils.http import Conflict, NotFound, ValidationError
from app.utils.money import parse_amount, parse_rate_percent

ENTITY = "loan_application"


def get(application_id: int) -> LoanApplication:
    row = db.session.get(LoanApplication, application_id)
    if row is None:
        raise NotFound("Application not found.")
    return row


def lock(application_id: int) -> LoanApplication:
    row = (db.session.query(LoanApplication).filter_by(id=application_id).with_for_update().one_or_none())
    if row is None:
        raise NotFound("Application not found.")
    return row


def _term(value, product: str) -> int:
    label, lo, hi, _ = PRODUCTS[product]
    try:
        term = int(str(value).strip())
    except (TypeError, ValueError):
        raise ValidationError("term_months must be a whole number of months.")
    if not lo <= term <= hi:
        raise ValidationError(f"A {label.lower()} runs {lo} to {hi} months (WA-04).")
    return term


def create(data: dict, actor) -> LoanApplication:
    party = parties.get_party(int(data.get("party_id") or 0))
    if party.status == "merged":
        raise Conflict("This client was merged into another record.")
    product = str(data.get("product_code") or "").strip()
    if product not in PRODUCTS:
        raise ValidationError(f"product_code must be one of: {', '.join(PRODUCTS)}.")
    amount = parse_amount(data.get("amount_requested"), "amount_requested")
    term = _term(data.get("term_months"), product)
    rate = parse_rate_percent(data.get("indicative_rate_percent"), "indicative_rate_percent")
    start = parse_date(data.get("business_start_date"), "business_start_date", required=False)
    if start and start > today_eat():
        raise ValidationError("business_start_date can't be in the future.")
    instalment, final = estimate(product, amount, term, rate)
    number = db.session.execute(application_no_seq.next_value()).scalar()
    row = LoanApplication(application_no=f"AP-{number:07d}", party_id=party.id, product_code=product,
                          amount_requested=amount, term_months=term, indicative_rate_percent=rate,
                          estimated_instalment=instalment, estimated_final_payment=final,
                          business_start_date=start, status="open", branch_id=party.home_branch_id,
                          created_by=actor.email, created_at=utcnow())
    db.session.add(row)
    db.session.flush()
    create_audit_log("CREATE_APPLICATION", target_type="loan_application", target_id=row.id,
                     target_name=row.application_no,
                     description=f"{PRODUCTS[product][0]} for {party.party_no}, estimated instalment {instalment}",
                     new_value=row.to_dict())
    db.session.commit()
    return row


def assert_open(row: LoanApplication) -> None:
    if row.status != "open":
        raise Conflict("A decision has been recorded on this application; it can't be changed.")


def guarantor_ids(application_id: int) -> list[int]:
    return [g.party_id for g in ApplicationParty.query.filter_by(application_id=application_id, role="guarantor")]


def add_guarantor(application_id: int, party_id: int, actor) -> ApplicationParty:
    row = lock(application_id)
    assert_open(row)
    party = parties.get_party(party_id)
    if party.id == row.party_id:
        raise ValidationError("The applicant can't guarantee their own application.")
    if party.id in guarantor_ids(row.id):
        raise Conflict(f"{party.display_name} is already a guarantor.")
    link = ApplicationParty(application_id=row.id, party_id=party.id, role="guarantor", added_by=actor.email)
    db.session.add(link)
    create_audit_log("ADD_APPLICATION_GUARANTOR", target_type="loan_application", target_id=row.id,
                     target_name=row.application_no, description=f"Guarantor {party.party_no}",
                     new_value={"party_id": party.id})
    db.session.commit()
    return link


def link_document(application_id: int, document_id, actor) -> DocumentLink:
    """A document already uploaded to the applicant or a guarantor, used for this application."""
    row = lock(application_id)
    assert_open(row)
    try:
        doc_id = uuid.UUID(str(document_id))
    except ValueError:
        raise NotFound("Document not found.")
    owners = {str(row.party_id), *map(str, guarantor_ids(row.id))}
    owned = DocumentLink.query.filter(DocumentLink.document_id == doc_id, DocumentLink.entity_type == "party",
                                      DocumentLink.entity_id.in_(owners)).first()
    if owned is None or db.session.get(Document, doc_id) is None:
        raise NotFound("Document not found for the applicant or a guarantor.")
    if DocumentLink.query.filter_by(document_id=doc_id, entity_type=ENTITY, entity_id=str(row.id)).first():
        raise Conflict("This document is already part of the application.")
    link = DocumentLink(document_id=doc_id, entity_type=ENTITY, entity_id=str(row.id), purpose="application",
                        linked_by=actor.email)
    db.session.add(link)
    create_audit_log("LINK_APPLICATION_DOCUMENT", target_type="loan_application", target_id=row.id,
                     target_name=row.application_no, description=f"Document {doc_id}",
                     new_value={"document_id": str(doc_id)})
    db.session.commit()
    return link


def document_ids(application_id: int) -> list[uuid.UUID]:
    return [l.document_id for l in DocumentLink.query.filter_by(entity_type=ENTITY, entity_id=str(application_id))]


def latest_extractions(application_id: int) -> list[Extraction]:
    """The newest finished extraction of each document in the application."""
    ids = document_ids(application_id)
    if not ids:
        return []
    rows = (Extraction.query.filter(Extraction.document_id.in_(ids), Extraction.status.in_(EXTRACTION_FINISHED))
            .order_by(Extraction.document_id, Extraction.requested_at.desc(), Extraction.id.desc()).all())
    seen, out = set(), []
    for r in rows:
        if r.document_id not in seen:
            seen.add(r.document_id)
            out.append(r)
    return out


def enter_crb(application_id: int, data: dict, actor) -> ApplicationCrbStatus:
    """Staff enter the CRB result (or take it from a reviewed CRB report); a second person confirms it."""
    row = lock(application_id)
    assert_open(row)
    status = str(data.get("status") or "").strip()
    if status not in CRB_STATUSES:
        raise ValidationError(f"status must be one of: {', '.join(CRB_STATUSES)}.")
    status_date = parse_date(data.get("status_date"), "status_date")
    if status_date > today_eat():
        raise ValidationError("status_date can't be in the future.")
    bureau = " ".join(str(data.get("bureau") or "").split())[:80]
    if not bureau:
        raise ValidationError("bureau is required.")
    extraction_id = data.get("extraction_id")
    if extraction_id not in (None, ""):
        ex = db.session.get(Extraction, int(extraction_id))
        if ex is None or ex.declared_type != "crb_report" or ex.document_id not in document_ids(row.id):
            raise ValidationError("extraction_id must be a CRB report reading in this application.")
        extraction_id = ex.id
    else:
        extraction_id = None
    pending = (ApplicationCrbStatus.query.filter_by(application_id=row.id, confirmed_at=None)
               .filter(ApplicationCrbStatus.change_request_id.isnot(None)).all())
    if any(_cr_open(c.change_request_id) for c in pending):
        raise Conflict("A CRB status for this application is already waiting for confirmation.")
    crb = ApplicationCrbStatus(application_id=row.id, status=status, status_date=status_date, bureau=bureau,
                               extraction_id=extraction_id, entered_by=actor.email, entered_at=utcnow())
    db.session.add(crb)
    db.session.flush()
    cr = approvals.submit("application.crb_confirm", {"crb_status_id": crb.id}, actor, commit=False)
    crb.change_request_id = cr.id
    create_audit_log("ENTER_CRB_STATUS", target_type="loan_application", target_id=row.id,
                     target_name=row.application_no, description=f"{CRB_LABELS[status]} ({bureau}, {status_date})",
                     new_value=crb.to_dict())
    db.session.commit()
    return crb


def _cr_open(request_id: int | None) -> bool:
    from app.Approvals.model import CR_OPEN, ChangeRequest
    cr = db.session.get(ChangeRequest, request_id) if request_id else None
    return cr is not None and cr.status in CR_OPEN


def confirmed_crb(application_id: int) -> ApplicationCrbStatus | None:
    return (ApplicationCrbStatus.query.filter(ApplicationCrbStatus.application_id == application_id,
                                              ApplicationCrbStatus.confirmed_at.isnot(None))
            .order_by(ApplicationCrbStatus.confirmed_at.desc(), ApplicationCrbStatus.id.desc()).first())


def list_applications(queue: str | None = None, search: str | None = None):
    from app.Parties.model import Party

    q = LoanApplication.query.join(Party, Party.id == LoanApplication.party_id)
    if queue == "ready_for_credit":
        from app.Applications.screening import ready_for_credit_ids
        q = q.filter(LoanApplication.id.in_(ready_for_credit_ids() or [0]))
    if search:
        like = f"%{search.strip()}%"
        q = q.filter(or_(LoanApplication.application_no.ilike(like), Party.display_name.ilike(like),
                         Party.party_no.ilike(like)))
    return q.order_by(LoanApplication.created_at.desc(), LoanApplication.id.desc())


def list_row(row: LoanApplication) -> dict:
    from app.Parties.model import Party

    from app.Applications.screening import decisions, latest_run

    party = db.session.get(Party, row.party_id)
    run = latest_run(row.id)
    last = (decisions(row.id) or [None])[-1]
    return {**row.to_dict(), "party": party.summary() if party else None,
            "recommendation": run.outcome if run else None, "decision": last["decision"] if last else None}


def documents(application_id: int) -> list[dict]:
    """The application's documents, each with its newest reading (if any)."""
    from app.DocAI import types

    ids = document_ids(application_id)
    docs = {d.id: d for d in Document.query.filter(Document.id.in_(ids))} if ids else {}
    readings = {}
    for ex in (Extraction.query.filter(Extraction.document_id.in_(ids)).order_by(Extraction.requested_at.desc(),
                                                                                  Extraction.id.desc()).all()
               if ids else []):
        readings.setdefault(ex.document_id, ex)
    out = []
    for doc_id in ids:
        doc, ex = docs[doc_id], readings.get(doc_id)
        out.append({"id": str(doc.id), "document_type": doc.document_type, "label": types.label(doc.document_type),
                    "filename": doc.original_filename, "content_type": doc.content_type, "status": doc.status,
                    "uploaded_at": doc.uploaded_at.isoformat(),
                    "extraction": ex.to_dict() if ex else None})
    return out


def detail(application_id: int) -> dict:
    from app.Applications.screening import screening_summary

    row = get(application_id)
    return {**summary(row), "documents": documents(row.id), **screening_summary(row.id)}


def summary(row: LoanApplication) -> dict:
    from app.Parties.model import Party

    party = db.session.get(Party, row.party_id)
    crb = confirmed_crb(row.id)
    return {**row.to_dict(), "party": party.summary() if party else None,
            "guarantors": [db.session.get(Party, pid).summary() for pid in guarantor_ids(row.id)],
            "crb": crb.to_dict() if crb else None}
