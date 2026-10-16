"""
The single client view (FSD v0.1 KYC-09): everything Anchorstone holds for one
person or organisation, whatever their roles: accounts (with balances), loans
and guarantees, directorships and other links, documents, consents, screening
and the changes waiting for approval.

Loans arrive with phase 5; until then the list is empty and guarantees are the
guarantor links recorded on the client.
"""
from app.Approvals import service as approvals
from app.Approvals.model import CR_OPEN, ChangeRequest
from app.database.database import db
from app.Parties import consent, documents, service
from app.Parties.model import Account, Party, ScreeningResult
from app.Transactions.ledger import investor_totals
from app.utils.money import as_str


def _accounts(party_id: int) -> list[dict]:
    from app.Investors.model import Investor

    out = []
    for account in Account.query.filter_by(party_id=party_id).order_by(Account.opened_on, Account.id):
        row = account.to_dict()
        investor = Investor.query.filter_by(account_id=account.id).first()
        if investor is not None:
            totals = investor_totals(investor.id)
            row.update({"investor_id": investor.id, "statement_email": investor.email,
                        "balance": as_str(totals["balance"]), "pending_withdrawals": as_str(totals["pending_withdrawals"]),
                        "interest_paid": as_str(totals["interest_paid"])})
        out.append(row)
    return out


def pending_changes(party_id: int, actor) -> list[dict]:
    rows = (ChangeRequest.query.filter(ChangeRequest.entity_type == "party", ChangeRequest.entity_id == str(party_id),
                                       ChangeRequest.status.in_(CR_OPEN))
            .order_by(ChangeRequest.submitted_at.desc()).all())
    return [{**cr.to_dict(approvals.summary(cr)), "can_decide": approvals.can_decide(cr, actor)} for cr in rows]


def overview(party: Party, actor) -> dict:
    detail = service.party_detail(party)
    rels = detail["relationships"]
    return {
        **detail,
        "accounts": _accounts(party.id),
        "loans": [],
        "guarantees": [r for r in rels if r["relationship"] == "guarantor_of" and r["direction"] == "outgoing"],
        "directorships": [r for r in rels if r["relationship"] in ("director", "shareholder", "signatory")
                          and r["direction"] == "outgoing"],
        "documents": documents.for_party(party.id),
        "consents": [c.to_dict() for c in consent.for_party(party.id)],
        "screening_results": [r.to_dict() for r in ScreeningResult.query.filter_by(party_id=party.id)
                              .order_by(ScreeningResult.screened_at.desc(), ScreeningResult.id.desc())],
        "pending_changes": pending_changes(party.id, actor),
        "merged_into": (db.session.get(Party, party.merged_into_party_id).summary()
                        if party.merged_into_party_id else None),
    }
