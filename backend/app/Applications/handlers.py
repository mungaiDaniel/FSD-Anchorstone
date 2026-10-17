"""
Change requests for pre-screen applications (maker-checker through app/Approvals).

    application.crb_confirm   a second person confirms a CRB status before the rules see it
                              (entered by hand or proposed from a CRB report reading)
"""
from app.Applications.model import CRB_LABELS, ApplicationCrbStatus, LoanApplication
from app.Approvals.handlers import Handler, register
from app.database.database import db
from app.utils.dates import utcnow
from app.utils.http import Conflict, ValidationError


@register
class ConfirmCrbStatus(Handler):
    request_type = "application.crb_confirm"
    entity_type = "loan_application"
    submit_permission = "application.manage"

    def _row(self, payload) -> ApplicationCrbStatus:
        crb_id = payload.get("crb_status_id")
        row = db.session.get(ApplicationCrbStatus, crb_id) if isinstance(crb_id, int) else None
        if row is None:
            raise ValidationError("crb_status_id must be a CRB status entry.")
        return row

    def validate(self, payload):
        row = self._row(payload)
        if row.confirmed_at is not None:
            raise Conflict("This CRB status is already confirmed.")
        app = db.session.get(LoanApplication, row.application_id)
        if app.status != "open":
            raise Conflict("A decision has been recorded on this application.")
        return {"crb_status_id": row.id}

    def entity_id(self, payload):
        return str(self._row(payload).application_id)

    def branch_id(self, payload):
        app = db.session.get(LoanApplication, self._row(payload).application_id)
        return app.branch_id if app else None

    def base_version(self, payload):
        row = self._row(payload)
        return f"{row.status}:{row.status_date}:{row.bureau}:{row.confirmed_at}"

    def describe(self, payload):
        row = self._row(payload)
        app = db.session.get(LoanApplication, row.application_id)
        return (f"Confirm CRB status for {app.application_no}: {CRB_LABELS[row.status]} "
                f"({row.bureau}, {row.status_date.isoformat()})")

    def apply(self, request, actor):
        row = (db.session.query(ApplicationCrbStatus).filter_by(id=request.payload["crb_status_id"])
               .with_for_update().one())
        row.confirmed_by, row.confirmed_at = actor.email, utcnow()
        db.session.flush()
        return row.to_dict()
