from flask import Blueprint, make_response, request

from app.Admin.model import ROLE_LEVELS
from app.auth import actor_email, current_user, staff_required, super_admin_required
from app.Reports import scheduled
from app.Reports.excel import XLSX_MIME
from app.Reports.model import ReportSchedule
from app.Reports.reports import REPORTS
from app.database.database import db
from app.utils.audit_log import create_audit_log
from app.utils.http import Forbidden, NotFound, ok

reports_v1 = Blueprint("reports_v1", __name__)


@reports_v1.get("/api/v1/reports")
@staff_required
def list_reports():
    level = current_user().role_level
    return ok([{"name": name, "title": title, "min_role": role}
               for name, (_, role, title) in REPORTS.items() if level >= ROLE_LEVELS[role]])


@reports_v1.get("/api/v1/reports/<name>.xlsx")
@staff_required
def export_report(name):
    if name not in REPORTS:
        raise NotFound("Unknown report.")
    builder, min_role, title = REPORTS[name]
    # Same access as the screen showing that data: the audit and email logs are admin-only.
    if current_user().role_level < ROLE_LEVELS[min_role]:
        raise Forbidden("You do not have permission to export this report.")

    report = builder(request.args)
    create_audit_log(
        "EXPORT_REPORT", target_type="report", target_name=name,
        description=f"{title}: {report.description} ({report.rows} rows)",
        new_value={k: v for k, v in request.args.items() if k != "token"},
    )
    response = make_response(report.data)
    response.headers["Content-Type"] = XLSX_MIME
    response.headers["Content-Disposition"] = f'attachment; filename="{report.filename}"'
    response.headers["Cache-Control"] = "no-store"
    return response


# ── Scheduled report settings (super admin) ──────────────────────────────


@reports_v1.get("/api/v1/settings/scheduled-reports")
@super_admin_required
def get_schedule():
    row = ReportSchedule.get(db.session)
    db.session.commit()
    return ok(row.to_dict())


@reports_v1.patch("/api/v1/settings/scheduled-reports")
@super_admin_required
def patch_schedule():
    row = scheduled.save_schedule(request.get_json(silent=True) or {}, actor_email())
    return ok(row.to_dict(), "Scheduled report settings saved.")


@reports_v1.post("/api/v1/settings/scheduled-reports/run-now")
@super_admin_required
def run_schedule_now():
    emails = scheduled.run_now(actor_email())
    return ok({"generated": len(emails)},
              f"AUM summary generated for {len(emails)} recipient(s). Confirm it on the Emails page to send it.", 201)
