from datetime import datetime, time, timedelta

from flask import Blueprint, request
from sqlalchemy import func, or_

from app.auth import requires
from app.database.database import db
from app.utils.audit_log import AuditLog
from app.utils.dates import EAT, parse_date
from app.utils.http import ok, page_args, paginate

audit_v1 = Blueprint("audit_v1", __name__)


def filtered_audit_logs(args):
    """Audit log rows newest first, filtered by action, target type, user (email
    or name contains) and an inclusive date range in Nairobi time. Shared by the
    Audit Log screen and the Excel export (app/Reports)."""
    q = db.session.query(AuditLog).order_by(AuditLog.timestamp.desc())
    if args.get("action"):
        q = q.filter(AuditLog.action == args["action"])
    if args.get("target_type"):
        q = q.filter(AuditLog.target_type == args["target_type"])
    user = (args.get("user") or "").strip().lower()
    if user:
        like = f"%{user}%"
        q = q.filter(or_(func.lower(AuditLog.user_email).like(like), func.lower(AuditLog.user_name).like(like)))
    start = parse_date(args.get("from"), "from", required=False)
    end = parse_date(args.get("to"), "to", required=False)
    if start:
        q = q.filter(AuditLog.timestamp >= datetime.combine(start, time.min, EAT))
    if end:
        q = q.filter(AuditLog.timestamp < datetime.combine(end + timedelta(days=1), time.min, EAT))
    return q


@audit_v1.get("/api/v1/audit-logs")
@requires("audit.view")
def get_audit_logs():
    page, per_page = page_args(request.args)
    return ok(paginate(filtered_audit_logs(request.args), page, per_page, lambda r: r.to_dict()))
