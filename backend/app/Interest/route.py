from flask import Blueprint, make_response, request

from app.database.database import db
from app.auth import actor_email, admin_required, staff_required
from app.Interest import service
from app.Interest.model import InterestPayout, InterestPeriod
from app.Transactions.ledger import locked_through
from app.utils.dates import iso
from app.utils.http import NotFound, ok
from app.Emails.model import EMAIL_INTEREST_STATEMENT, EmailAttachment, OutboxEmail
from app.utils.pdf_generator import generate_interest_statement_pdf, interest_statement_filename

interest_v1 = Blueprint("interest_v1", __name__)


@interest_v1.get("/api/v1/interest/rates")
@staff_required
def list_rates():
    current = service.current_rate()
    return ok({
        "current": current.to_dict() if current else None,
        "history": [r.to_dict() for r in service.list_rates()],
        "locked_through": iso(locked_through()),
    })


@interest_v1.post("/api/v1/interest/rates")
@admin_required
def set_rate():
    rate = service.set_rate(request.get_json(silent=True) or {}, actor_email())
    return ok(rate.to_dict(), "Interest rate saved.", 201)


@interest_v1.get("/api/v1/interest/periods")
@staff_required
def list_periods():
    periods = InterestPeriod.query.order_by(InterestPeriod.period_start.desc()).all()
    return ok({"items": [p.to_dict() for p in periods], "locked_through": iso(locked_through())})


@interest_v1.post("/api/v1/interest/periods/calculate")
@admin_required
def calculate_period():
    period = service.calculate_period(request.get_json(silent=True) or {}, actor_email())
    return ok(period.to_dict(), f"Draft calculated for {period.label}. Another admin must review and approve it.", 201)


@interest_v1.get("/api/v1/interest/periods/<int:period_id>")
@staff_required
def get_period(period_id):
    period = service.get_period(period_id)
    return ok({**period.to_dict(), "payouts": [p.to_dict() for p in service.period_payouts(period)]})


@interest_v1.delete("/api/v1/interest/periods/<int:period_id>")
@admin_required
def discard_draft(period_id):
    service.discard_draft(period_id, actor_email())
    return ok(message="Draft discarded.")


@interest_v1.post("/api/v1/interest/periods/<int:period_id>/approve")
@admin_required
def approve_period(period_id):
    period = service.approve_period(period_id, actor_email())
    return ok(period.to_dict(), f"{period.label} approved. Statements have been queued to {period.investor_count} investors.")


@interest_v1.post("/api/v1/interest/periods/<int:period_id>/mark-paid")
@admin_required
def mark_paid(period_id):
    period = service.mark_payouts_paid(period_id, request.get_json(silent=True) or {}, actor_email())
    return ok(period.to_dict(), "Payouts marked paid.")


@interest_v1.get("/api/v1/interest/payouts/<int:payout_id>/statement.pdf")
@staff_required
def payout_statement_pdf(payout_id):
    payout = db.session.get(InterestPayout, payout_id)
    if payout is None:
        raise NotFound("Payout not found.")
    # The statement as issued to the investor, if it has been; otherwise the current figures.
    issued = (
        EmailAttachment.query.join(OutboxEmail, OutboxEmail.id == EmailAttachment.email_id)
        .filter(OutboxEmail.payout_id == payout.id, OutboxEmail.email_type == EMAIL_INTEREST_STATEMENT)
        .first()
    )
    pdf = issued.data if issued is not None else generate_interest_statement_pdf(payout_id)
    filename = interest_statement_filename(payout)
    response = make_response(pdf)
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = f'inline; filename="{filename}"'
    return response
