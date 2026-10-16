"""Phase 2a item 4: permission-based access that reproduces the old three roles exactly."""
from datetime import date
from decimal import Decimal

import pytest

from app.Access.model import Role, RolePermission, TransactionLimit, UserBranchScope, UserRole
from app.Access.service import branch_scope, limit_for, permissions_for
from app.Admin.model import ROLE_LEVELS
from app.Branches.model import Branch
from app.database.database import db
from app.utils.dates import utcnow
from conftest import Api, _make_user

# The decorator each endpoint had before permissions (snapshot of phase 1).
OLD_MIN_ROLE = {
    ("GET", "/api/v1/users"): "super_admin",
    ("POST", "/api/v1/users"): "super_admin",
    ("GET", "/api/v1/users/<int:user_id>"): "super_admin",
    ("PATCH", "/api/v1/users/<int:user_id>/status"): "super_admin",
    ("PATCH", "/api/v1/users/<int:user_id>/role"): "super_admin",
    ("POST", "/api/v1/users/<int:user_id>/reset-password"): "super_admin",
    ("POST", "/api/v1/users/<int:user_id>/unlock"): "admin",
    ("DELETE", "/api/v1/users/<int:user_id>"): "super_admin",
    ("GET", "/api/v1/audit-logs"): "admin",
    ("GET", "/api/v1/backups"): "super_admin",
    ("GET", "/api/v1/backups/status"): "super_admin",
    ("POST", "/api/v1/backups/run-now"): "super_admin",
    ("GET", "/api/v1/emails"): "user",
    ("GET", "/api/v1/emails/status"): "user",
    ("POST", "/api/v1/emails/<int:email_id>/retry"): "admin",
    ("POST", "/api/v1/emails/<int:email_id>/cancel"): "admin",
    ("POST", "/api/v1/emails/send-now"): "admin",
    ("POST", "/api/v1/investors/<int:investor_id>/statement-email"): "admin",
    ("POST", "/api/v1/emails/statements/bulk"): "admin",
    ("POST", "/api/v1/emails/confirm"): "admin",
    ("POST", "/api/v1/emails/suppress"): "admin",
    ("GET", "/api/v1/emails/<int:email_id>/attachment"): "user",
    ("GET", "/api/v1/interest/rates"): "user",
    ("POST", "/api/v1/interest/rates"): "admin",
    ("GET", "/api/v1/interest/periods"): "user",
    ("POST", "/api/v1/interest/periods/calculate"): "admin",
    ("GET", "/api/v1/interest/periods/<int:period_id>"): "user",
    ("DELETE", "/api/v1/interest/periods/<int:period_id>"): "admin",
    ("POST", "/api/v1/interest/periods/<int:period_id>/approve"): "admin",
    ("POST", "/api/v1/interest/periods/<int:period_id>/mark-paid"): "admin",
    ("GET", "/api/v1/interest/payouts/<int:payout_id>/statement.pdf"): "user",
    ("GET", "/api/v1/investors"): "user",
    ("POST", "/api/v1/investors"): "user",
    ("GET", "/api/v1/investors/<int:investor_id>"): "user",
    ("PATCH", "/api/v1/investors/<int:investor_id>"): "user",
    ("PATCH", "/api/v1/investors/<int:investor_id>/status"): "admin",
    ("GET", "/api/v1/investors/<int:investor_id>/ledger"): "user",
    ("GET", "/api/v1/investors/<int:investor_id>/deposits"): "user",
    ("GET", "/api/v1/investors/<int:investor_id>/withdrawals"): "user",
    ("GET", "/api/v1/investors/<int:investor_id>/payouts"): "user",
    ("GET", "/api/v1/investors/<int:investor_id>/emails"): "user",
    ("GET", "/api/v1/reports"): "user",
    ("GET", "/api/v1/reports/<name>.xlsx"): "user",
    ("GET", "/api/v1/settings/scheduled-reports"): "super_admin",
    ("PATCH", "/api/v1/settings/scheduled-reports"): "super_admin",
    ("POST", "/api/v1/settings/scheduled-reports/run-now"): "super_admin",
    ("GET", "/api/v1/settings/email"): "super_admin",
    ("PATCH", "/api/v1/settings/email"): "super_admin",
    ("POST", "/api/v1/settings/email/test"): "super_admin",
    ("GET", "/api/v1/settings/email-queue"): "super_admin",
    ("PATCH", "/api/v1/settings/email-queue"): "super_admin",
    ("GET", "/api/v1/stats/overview"): "user",
    ("GET", "/api/v1/deposits"): "user",
    ("POST", "/api/v1/deposits"): "user",
    ("POST", "/api/v1/deposits/<int:deposit_id>/reverse"): "admin",
    ("GET", "/api/v1/withdrawals"): "user",
    ("POST", "/api/v1/withdrawals"): "user",
    ("POST", "/api/v1/withdrawals/<int:withdrawal_id>/approve"): "admin",
    ("POST", "/api/v1/withdrawals/<int:withdrawal_id>/reject"): "admin",
}
# Old per-report rule (inside the export route).
OLD_REPORT_ROLE = {"investors": "user", "deposits": "user", "withdrawals": "user", "interest": "user",
                   "aum": "user", "audit-log": "admin", "email-log": "admin"}
PUBLIC = {("POST", "/api/v1/login"), ("GET", "/api/v1/health")}
SELF_SERVICE = {("GET", "/api/v1/me"), ("POST", "/api/v1/me/password")}
# Endpoints added after phase 1 (by later 2a commits); checked by their own tests.
NEW_SINCE_PHASE_1 = {
    ("GET", "/api/v1/change-requests"), ("POST", "/api/v1/change-requests"),
    ("GET", "/api/v1/change-requests/<int:request_id>"),
    *(("POST", f"/api/v1/change-requests/<int:request_id>/{a}")
      for a in ("approve", "reject", "return", "resubmit", "cancel")),
    ("GET", "/api/v1/settings/business"), ("POST", "/api/v1/settings/business/<key>"),
}


def _routes(app):
    out = {}
    for rule in app.url_map.iter_rules():
        if rule.endpoint == "static":
            continue
        view = app.view_functions[rule.endpoint]
        for method in rule.methods - {"HEAD", "OPTIONS"}:
            out[(method, rule.rule)] = view
    return out


def test_every_route_is_guarded_by_requires(app):
    for key, view in _routes(app).items():
        if key in PUBLIC:
            continue
        assert hasattr(view, "required_permissions"), f"{key} has no @requires"
        if key in SELF_SERVICE:
            assert view.required_permissions == () and view.allows_temporary_password
        else:
            assert view.required_permissions, f"{key} requires no permission"
            assert not view.allows_temporary_password


def test_route_table_is_complete(app):
    known = set(OLD_MIN_ROLE) | PUBLIC | SELF_SERVICE | NEW_SINCE_PHASE_1
    assert set(_routes(app)) - known == set(), "new route: add it to OLD_MIN_ROLE or NEW_SINCE_PHASE_1"
    assert set(OLD_MIN_ROLE) - set(_routes(app)) == set(), "route removed"


@pytest.mark.parametrize("legacy_role", ["user", "admin", "super_admin"])
def test_built_in_roles_allow_exactly_what_the_old_decorators_allowed(app, legacy_role):
    user = _make_user(f"{legacy_role}@anchorstone.test", legacy_role)
    held = permissions_for(user)
    routes = _routes(app)
    for key, min_role in OLD_MIN_ROLE.items():
        allowed_before = ROLE_LEVELS[legacy_role] >= ROLE_LEVELS[min_role]
        allowed_now = all(p in held for p in routes[key].required_permissions)
        assert allowed_now == allowed_before, f"{legacy_role} on {key}: before {allowed_before}, now {allowed_now}"
    for name, min_role in OLD_REPORT_ROLE.items():
        assert (f"report.export.{name}" in held) == (ROLE_LEVELS[legacy_role] >= ROLE_LEVELS[min_role]), name


def test_built_in_roles_map_to_the_legacy_values():
    assert {r.legacy_role: r.code for r in Role.query.filter(Role.legacy_role.isnot(None))} == {
        "user": "ops_staff", "admin": "ops_admin", "super_admin": "system_admin"}


def test_fsd_roles_exist_but_are_inactive_and_unassigned():
    codes = {"credit_officer", "credit_manager", "credit_committee", "board_credit_committee", "finance", "risk_audit"}
    roles = Role.query.filter(Role.code.in_(codes)).all()
    assert {r.code for r in roles} == codes
    assert all(not r.active and not r.built_in and r.legacy_role is None for r in roles)
    assert UserRole.query.count() == 0


def _grant(user, role):
    db.session.add(UserRole(user_id=user.id, role_id=role.id, granted_by="test", granted_at=utcnow()))
    db.session.commit()


def _custom_role(code, perms, **kw):
    role = Role(code=code, name=code.title(), **kw)
    db.session.add(role)
    db.session.flush()
    for p in perms:
        db.session.add(RolePermission(role_id=role.id, permission_code=p))
    db.session.commit()
    return role


def test_custom_role_grants_only_its_permissions_and_revoking_is_immediate(client, users, staff):
    assert staff.get("/api/v1/audit-logs").status_code == 403
    role = _custom_role("auditor_test", ["audit.view"])
    _grant(users["staff"], role)
    assert staff.get("/api/v1/audit-logs").status_code == 200
    assert staff.post("/api/v1/interest/rates", {"rate_percent": "10", "effective_from": "2026-01-01"}).status_code == 403

    UserRole.query.filter_by(user_id=users["staff"].id).delete()
    db.session.commit()
    assert staff.get("/api/v1/audit-logs").status_code == 403


def test_inactive_role_grants_nothing(users, staff):
    _grant(users["staff"], Role.query.filter_by(code="risk_audit").one())
    assert staff.get("/api/v1/audit-logs").status_code == 403


def test_a_user_with_no_role_permissions_is_refused_everywhere(client):
    # A primary role whose built-in bundle is deactivated holds nothing.
    user = _make_user("lonely@anchorstone.test", "user")
    Role.query.filter_by(legacy_role="user").update({"active": False})
    db.session.commit()
    api = Api(client, user.email)
    assert api.get("/api/v1/investors").status_code == 403
    assert api.get("/api/v1/me").status_code == 200  # self-service still works


def test_report_export_follows_its_permission(users, staff):
    assert staff.get("/api/v1/reports/audit-log.xlsx").status_code == 403
    _grant(users["staff"], _custom_role("log_reader", ["report.export.audit-log"]))
    assert staff.get("/api/v1/reports/audit-log.xlsx").status_code == 200
    names = {r["name"] for r in staff.get("/api/v1/reports").get_json()["data"]}
    assert "audit-log" in names and "email-log" not in names


def test_me_lists_permissions_and_branch_scope(staff, superadmin):
    me = staff.get("/api/v1/me").get_json()["data"]
    assert "deposit.record" in me["permissions"] and "deposit.reverse" not in me["permissions"]
    assert me["branch_scope"] is None  # built-in roles see every branch
    assert me["role"] == "user" and me["branch_id"] == 1
    assert "user.manage" in superadmin.get("/api/v1/me").get_json()["data"]["permissions"]


def test_branch_scope_from_rows_or_home_branch(users):
    custom = _make_user("branchy@anchorstone.test", "user")
    Role.query.filter_by(legacy_role="user").update({"all_branches": False})
    db.session.commit()
    assert branch_scope(custom) == frozenset({1})
    db.session.add(Branch(code="001", name="Westlands"))
    db.session.flush()
    westlands = Branch.query.filter_by(code="001").one()
    db.session.add(UserBranchScope(user_id=custom.id, branch_id=westlands.id, granted_by="test"))
    db.session.commit()
    assert branch_scope(custom) == frozenset({westlands.id})
    db.session.add(UserBranchScope(user_id=custom.id, all_branches=True, granted_by="test"))
    db.session.commit()
    assert branch_scope(custom) is None


class TestTransactionLimits:
    def test_built_in_approvers_are_unlimited(self, users):
        for who in ("admin1", "super"):
            limit = limit_for(users[who], "withdrawal.approve")
            assert limit.configured and limit.max_per_item is None
            assert limit.allows(Decimal("999999999999.99"))

    def test_no_limit_row_means_no_amount_can_be_decided(self, users):
        role = _custom_role("approver_no_limit", ["withdrawal.approve"])
        _grant(users["staff"], role)
        limit = limit_for(users["staff"], "withdrawal.approve")
        assert not limit.configured and not limit.allows(Decimal("1"))

    def test_highest_role_limit_applies_and_user_limit_overrides(self, users):
        small = _custom_role("approver_small", ["withdrawal.approve"])
        big = _custom_role("approver_big", ["withdrawal.approve"])
        _grant(users["staff"], small)
        _grant(users["staff"], big)
        for role, amount in ((small, "100000"), (big, "500000")):
            db.session.add(TransactionLimit(subject_type="role", subject_id=role.id, permission_code="withdrawal.approve",
                                            max_per_item=Decimal(amount), effective_from=date(2026, 1, 1), set_by="t"))
        db.session.commit()
        limit = limit_for(users["staff"], "withdrawal.approve")
        assert limit.max_per_item == Decimal("500000") and limit.source == "role:approver_big"
        assert limit.allows(Decimal("500000")) and not limit.allows(Decimal("500000.01"))

        db.session.add(TransactionLimit(subject_type="user", subject_id=users["staff"].id,
                                        permission_code="withdrawal.approve", max_per_item=Decimal("50000"),
                                        effective_from=date(2026, 1, 1), set_by="t"))
        db.session.commit()
        limit = limit_for(users["staff"], "withdrawal.approve")
        assert limit.source == "user" and not limit.allows(Decimal("50000.01"))

    def test_future_dated_limit_does_not_apply_yet(self, users):
        role = _custom_role("approver_future", ["withdrawal.approve"])
        _grant(users["staff"], role)
        db.session.add(TransactionLimit(subject_type="role", subject_id=role.id, permission_code="withdrawal.approve",
                                        max_per_item=Decimal("100"), effective_from=date(2027, 1, 1), set_by="t"))
        db.session.commit()
        assert not limit_for(users["staff"], "withdrawal.approve").configured

    def test_permissions_that_are_not_amount_limited_are_unlimited(self, users):
        assert limit_for(users["staff"], "deposit.record").allows(Decimal("1000000000"))
