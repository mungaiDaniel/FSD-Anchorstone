"""Phase 2a item 3: the generic maker-checker framework."""
import json
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.Access.model import Role, RolePermission, UserRole
from app.Approvals import service
from app.Approvals.handlers import HANDLERS, Handler
from app.Approvals.model import ApprovalPolicy, ChangeRequest
from app.Branches.model import Branch
from app.database.database import db
from app.utils.audit_log import AuditLog
from app.utils.dates import utcnow
from app.utils.http import ValidationError
from conftest import Api, _make_user

# ── A test-only handler, so lifecycle rules are tested without any business side effects ──

STATE = {"version": "v1", "applied": [], "valid": True}


class NoopHandler(Handler):
    request_type = "test.noop"
    entity_type = "test"
    submit_permission = "change_request.view"

    def validate(self, payload):
        if not STATE["valid"]:
            raise ValidationError("No longer valid.")
        return payload

    def base_version(self, payload):
        return STATE["version"]

    def amount(self, payload):
        return Decimal(payload["amount"]) if payload.get("amount") is not None else None

    def branch_id(self, payload):
        return payload.get("branch_id")

    def describe(self, payload):
        return f"Test change {payload.get('n')}"

    def apply(self, request, actor):
        STATE["applied"].append(request.payload.get("n"))
        return {"done": request.payload.get("n")}


HANDLERS.setdefault("test.noop", NoopHandler())


@pytest.fixture(autouse=True)
def _reset_state():
    STATE.update(version="v1", applied=[], valid=True)


def _policy(levels, min_amount=None, max_amount=None, request_type="test.noop"):
    db.session.add(ApprovalPolicy(request_type=request_type, levels=levels, min_amount=min_amount,
                                  max_amount=max_amount))
    db.session.commit()


def _role(code, perms):
    role = Role(code=code, name=code)
    db.session.add(role)
    db.session.flush()
    for p in perms:
        db.session.add(RolePermission(role_id=role.id, permission_code=p))
    db.session.commit()
    return role


def _grant(user, role):
    db.session.add(UserRole(user_id=user.id, role_id=role.id, granted_by="test", granted_at=utcnow()))
    db.session.commit()


def _submit(api, payload=None, request_type="test.noop", expect=201):
    res = api.post("/api/v1/change-requests", {"request_type": request_type, "payload": payload or {"n": 1}})
    assert res.status_code == expect, res.get_json()
    return res.get_json().get("data")


# ── Database-level guarantees (bypassing the service layer) ──


def test_database_refuses_a_decision_by_the_maker(users, admin1):
    _policy([{"permission": "change_request.view", "count": 1}])
    cr = _submit(admin1)
    for action in ("approve", "reject", "return"):
        with pytest.raises(IntegrityError, match="Maker-checker"):
            db.session.execute(text(
                "INSERT INTO change_request_events (request_id, round, action, level, actor_user_id, actor_email, at,"
                " date_created, date_updated) VALUES (:r, 1, :a, 1, :u, 'x', now(), now(), now())"),
                {"r": cr["id"], "a": action, "u": users["admin1"].id})
            db.session.flush()
        db.session.rollback()


def test_database_refuses_two_approvals_by_one_person_in_a_round(users, admin1):
    _policy([{"permission": "change_request.view", "count": 1}, {"permission": "change_request.view", "count": 1}])
    cr = _submit(admin1)
    insert = text("INSERT INTO change_request_events (request_id, round, action, level, actor_user_id, actor_email, at,"
                  " date_created, date_updated) VALUES (:r, 1, 'approve', :lvl, :u, 'x', now(), now(), now())")
    db.session.execute(insert, {"r": cr["id"], "lvl": 1, "u": users["admin2"].id})
    with pytest.raises(IntegrityError, match="uq_change_request_events_one_approval"):
        db.session.execute(insert, {"r": cr["id"], "lvl": 2, "u": users["admin2"].id})
        db.session.flush()
    db.session.rollback()


def test_change_request_events_are_insert_only(admin1):
    _policy([{"permission": "change_request.view", "count": 1}])
    _submit(admin1)
    for sql in ("UPDATE change_request_events SET comment = 'edited'", "DELETE FROM change_request_events"):
        with pytest.raises(DBAPIError, match="insert-only"):
            db.session.execute(text(sql))
            db.session.flush()
        db.session.rollback()


def test_database_refuses_withdrawal_decided_by_its_maker(make_investor, deposit, staff):
    inv = make_investor()
    deposit(inv["id"], "10000", "2026-09-01")
    staff.post("/api/v1/withdrawals", {"investor_id": inv["id"], "amount": "100", "requested_date": "2026-09-02",
                                       "method": "mpesa"})
    with pytest.raises(IntegrityError, match="ck_withdrawals_maker_not_checker"):
        db.session.execute(text("UPDATE withdrawals SET decided_by = upper(requested_by), status = 'rejected'"))
        db.session.flush()
    db.session.rollback()


def test_database_refuses_interest_approved_by_its_calculator(make_investor, deposit, rate, admin1):
    inv = make_investor()
    rate("12", "2026-01-01")
    deposit(inv["id"], "10000", "2026-08-01")
    assert admin1.post("/api/v1/interest/periods/calculate", {"year": 2026, "month": 8}).status_code == 201
    with pytest.raises(IntegrityError, match="ck_interest_periods_maker_not_checker"):
        db.session.execute(text("UPDATE interest_periods SET approved_by = calculated_by, status = 'approved'"))
        db.session.flush()
    db.session.rollback()


# ── Domain records on the shared rule ──


def test_maker_cannot_reject_their_own_withdrawal(make_investor, deposit, admin1, admin2):
    inv = make_investor()
    deposit(inv["id"], "10000", "2026-09-01")
    wid = admin1.post("/api/v1/withdrawals", {"investor_id": inv["id"], "amount": "100",
                                              "requested_date": "2026-09-02", "method": "mpesa"}).get_json()["data"]["id"]
    res = admin1.post(f"/api/v1/withdrawals/{wid}/reject", {"reason": "no"})
    assert res.status_code == 403 and res.get_json()["message"].startswith("Maker-checker")
    assert admin2.post(f"/api/v1/withdrawals/{wid}/reject", {"reason": "no"}).status_code == 200


def test_withdrawal_approval_respects_the_approvers_amount_limit(client, users, superadmin, make_investor, deposit, staff):
    other_super = _make_user("super2@anchorstone.test", "super_admin")
    approver = _make_user("approver@anchorstone.test", "user")
    _role("small_approver", ["withdrawal.approve"])
    super2 = Api(client, other_super.email)
    # Grant the role and a KES 1,000 limit, each approved by a second system administrator.
    for rt, payload in (("rbac.grant_role", {"user_id": approver.id, "role_code": "small_approver"}),
                        ("rbac.set_limit", {"subject_type": "user", "user_id": approver.id,
                                            "permission": "withdrawal.approve", "max_per_item": "1000"})):
        cr = _submit(superadmin, payload, rt)
        assert super2.post(f"/api/v1/change-requests/{cr['id']}/approve").status_code == 200

    inv = make_investor()
    deposit(inv["id"], "100000", "2026-09-01")
    big, small = (staff.post("/api/v1/withdrawals", {"investor_id": inv["id"], "amount": amt, "requested_date": "2026-09-02",
                                                     "method": "mpesa"}).get_json()["data"]["id"] for amt in ("5000", "500"))
    api = Api(client, approver.email)
    res = api.post(f"/api/v1/withdrawals/{big}/approve", {"value_date": "2026-09-02"})
    assert res.status_code == 403 and "above your approval limit" in res.get_json()["message"]
    assert api.post(f"/api/v1/withdrawals/{small}/approve", {"value_date": "2026-09-02"}).status_code == 200


# ── Lifecycle through the API ──


def test_submit_approve_applies_in_the_same_transaction_with_audit(admin1, admin2):
    _policy([{"permission": "change_request.view", "count": 1}])
    cr = _submit(admin1, {"n": 7})
    assert cr["status"] == "pending" and cr["summary"] == "Test change 7"
    assert admin1.post(f"/api/v1/change-requests/{cr['id']}/approve").status_code == 403  # maker
    res = admin2.post(f"/api/v1/change-requests/{cr['id']}/approve", {"comment": "fine"})
    assert res.status_code == 200 and res.get_json()["data"]["status"] == "applied"
    assert STATE["applied"] == [7]
    actions = [a.action for a in AuditLog.query.filter_by(target_type="change_request").order_by(AuditLog.id)]
    assert actions == ["CHANGE_REQUEST_SUBMITTED", "CHANGE_REQUEST_APPROVED", "CHANGE_REQUEST_APPLIED"]
    events = admin1.get(f"/api/v1/change-requests/{cr['id']}").get_json()["data"]["events"]
    assert [e["action"] for e in events] == ["submit", "approve", "apply"]


def test_two_levels_need_two_different_people(admin1, admin2, superadmin):
    _policy([{"permission": "change_request.view", "count": 1}, {"permission": "change_request.view", "count": 1}])
    cr = _submit(admin1)
    res = admin2.post(f"/api/v1/change-requests/{cr['id']}/approve")
    assert res.get_json()["data"]["status"] == "pending" and res.get_json()["data"]["levels_done"] == 1
    res = admin2.post(f"/api/v1/change-requests/{cr['id']}/approve")
    assert res.status_code == 403 and "already approved" in res.get_json()["message"]
    assert superadmin.post(f"/api/v1/change-requests/{cr['id']}/approve").get_json()["data"]["status"] == "applied"


def test_a_level_can_need_two_approvers(admin1, admin2, superadmin):
    _policy([{"permission": "change_request.view", "count": 2}])
    cr = _submit(admin1)
    assert admin2.post(f"/api/v1/change-requests/{cr['id']}/approve").get_json()["data"]["status"] == "pending"
    assert superadmin.post(f"/api/v1/change-requests/{cr['id']}/approve").get_json()["data"]["status"] == "applied"


def test_amount_selects_the_policy_and_limits_route_to_a_higher_approver(client, users, admin1, admin2):
    _policy([{"permission": "withdrawal.approve", "count": 1}], max_amount=Decimal("500000"))
    _policy([{"permission": "withdrawal.approve", "count": 1}, {"permission": "role.manage", "count": 1}],
            min_amount=Decimal("500000.01"))
    small = _submit(admin1, {"n": 1, "amount": "400000"})
    big = _submit(admin1, {"n": 2, "amount": "600000"})
    assert small["levels_required"] == 1 and big["levels_required"] == 2

    limited = _make_user("limited@anchorstone.test", "user")
    role = _role("limited_approver", ["withdrawal.approve", "change_request.view"])
    _grant(limited, role)
    db.session.execute(text("INSERT INTO transaction_limits (subject_type, subject_id, permission_code, max_per_item,"
                            " effective_from, set_by, date_created, date_updated) VALUES ('role', :r,"
                            " 'withdrawal.approve', 100000, '2026-01-01', 't', now(), now())"), {"r": role.id})
    db.session.commit()
    res = Api(client, limited.email).post(f"/api/v1/change-requests/{small['id']}/approve")
    assert res.status_code == 403 and "above your approval limit" in res.get_json()["message"]
    assert admin2.post(f"/api/v1/change-requests/{small['id']}/approve").get_json()["data"]["status"] == "applied"


def test_approver_without_the_level_permission_is_refused(admin1, staff):
    _policy([{"permission": "role.manage", "count": 1}])
    cr = _submit(admin1)
    res = staff.post(f"/api/v1/change-requests/{cr['id']}/approve")
    assert res.status_code == 403


def test_approver_outside_the_branch_is_refused(client, admin1, superadmin):
    db.session.add(Branch(code="001", name="Westlands"))
    db.session.commit()
    westlands = Branch.query.filter_by(code="001").one()
    _policy([{"permission": "change_request.view", "count": 1}])
    cr = _submit(admin1, {"n": 1, "branch_id": westlands.id})
    branch_user = _make_user("branch@anchorstone.test", "user")
    Role.query.filter_by(legacy_role="user").update({"all_branches": False})
    db.session.commit()
    res = Api(client, branch_user.email).post(f"/api/v1/change-requests/{cr['id']}/approve")
    assert res.status_code == 403 and "branch" in res.get_json()["message"]
    assert superadmin.post(f"/api/v1/change-requests/{cr['id']}/approve").status_code == 200


def test_stale_base_version_fails_with_the_documented_message(admin1, admin2):
    _policy([{"permission": "change_request.view", "count": 1}])
    cr = _submit(admin1)
    STATE["version"] = "v2"
    res = admin2.post(f"/api/v1/change-requests/{cr['id']}/approve")
    assert res.status_code == 409
    assert res.get_json()["message"] == "The record changed after this request was made. Submit a new request."
    assert db.session.get(ChangeRequest, cr["id"]).status == "failed"
    assert STATE["applied"] == []


def test_revalidation_at_approval_keeps_the_request_pending(admin1, admin2):
    _policy([{"permission": "change_request.view", "count": 1}])
    cr = _submit(admin1)
    STATE["valid"] = False
    assert admin2.post(f"/api/v1/change-requests/{cr['id']}/approve").status_code == 400
    db.session.expire_all()
    assert db.session.get(ChangeRequest, cr["id"]).status == "pending"


def test_returned_request_is_resubmitted_and_approved_in_a_new_round(admin1, admin2):
    _policy([{"permission": "change_request.view", "count": 1}])
    cr = _submit(admin1, {"n": 1})
    assert admin2.post(f"/api/v1/change-requests/{cr['id']}/return", {}).status_code == 400  # needs a reason
    assert admin2.post(f"/api/v1/change-requests/{cr['id']}/return", {"reason": "fix n"}).status_code == 200
    assert admin2.post(f"/api/v1/change-requests/{cr['id']}/approve").status_code == 409  # returned, not pending
    assert admin2.post(f"/api/v1/change-requests/{cr['id']}/resubmit", {"payload": {"n": 2}}).status_code == 403
    res = admin1.post(f"/api/v1/change-requests/{cr['id']}/resubmit", {"payload": {"n": 2}})
    assert res.get_json()["data"]["round"] == 2 and res.get_json()["data"]["status"] == "pending"
    assert admin2.post(f"/api/v1/change-requests/{cr['id']}/approve").get_json()["data"]["status"] == "applied"
    assert STATE["applied"] == [2]


def test_reject_needs_a_reason_and_is_final(admin1, admin2):
    _policy([{"permission": "change_request.view", "count": 1}])
    cr = _submit(admin1)
    assert admin2.post(f"/api/v1/change-requests/{cr['id']}/reject", {}).status_code == 400
    assert admin2.post(f"/api/v1/change-requests/{cr['id']}/reject", {"reason": "no"}).status_code == 200
    assert admin2.post(f"/api/v1/change-requests/{cr['id']}/approve").status_code == 409


def test_only_the_maker_can_cancel(admin1, admin2):
    _policy([{"permission": "change_request.view", "count": 1}])
    cr = _submit(admin1)
    assert admin2.post(f"/api/v1/change-requests/{cr['id']}/cancel").status_code == 403
    assert admin1.post(f"/api/v1/change-requests/{cr['id']}/cancel").get_json()["data"]["status"] == "cancelled"


def test_open_requests_expire(app, admin1, admin2):
    _policy([{"permission": "change_request.view", "count": 1}])
    cr = _submit(admin1)
    row = db.session.get(ChangeRequest, cr["id"])
    row.expires_at = utcnow() - timedelta(minutes=1)
    db.session.commit()
    assert service.expire_due() == 1
    assert db.session.get(ChangeRequest, cr["id"]).status == "expired"
    assert admin2.post(f"/api/v1/change-requests/{cr['id']}/approve").status_code == 409


def test_inbox_lists_only_what_i_may_decide(admin1, admin2):
    _policy([{"permission": "change_request.view", "count": 1}])
    cr = _submit(admin1)
    assert [r["id"] for r in admin2.get("/api/v1/change-requests").get_json()["data"]["items"]] == [cr["id"]]
    assert admin1.get("/api/v1/change-requests").get_json()["data"]["items"] == []
    assert [r["id"] for r in admin1.get("/api/v1/change-requests?mine=1").get_json()["data"]["items"]] == [cr["id"]]


def test_unknown_type_and_missing_policy_are_refused(admin1):
    _submit(admin1, request_type="nope", expect=400)
    _submit(admin1, expect=400)  # test.noop has no policy yet


# ── Access changes are change requests approved by a second system administrator ──


def test_role_grant_needs_a_second_system_administrator(client, users, superadmin, admin1):
    other = _make_user("super2@anchorstone.test", "super_admin")
    super2 = Api(client, other.email)
    payload = {"user_id": users["staff"].id, "role_code": "risk_audit"}
    _submit(admin1, payload, "rbac.grant_role", expect=403)  # admins can't request access changes
    cr = _submit(superadmin, payload, "rbac.grant_role")
    assert superadmin.post(f"/api/v1/change-requests/{cr['id']}/approve").status_code == 403
    assert admin1.post(f"/api/v1/change-requests/{cr['id']}/approve").status_code == 403
    res = super2.post(f"/api/v1/change-requests/{cr['id']}/approve")
    assert res.status_code == 200
    grant = UserRole.query.filter_by(user_id=users["staff"].id).one()
    assert grant.role.code == "risk_audit" and grant.via_change_request_id == cr["id"]
    _submit(superadmin, payload, "rbac.grant_role", expect=400)  # already granted


def test_built_in_roles_cannot_be_granted_as_extra_roles(users, superadmin):
    _submit(superadmin, {"user_id": users["staff"].id, "role_code": "ops_admin"}, "rbac.grant_role", expect=400)


def test_activating_a_role_and_setting_branch_scope(client, users, superadmin):
    super2 = Api(client, _make_user("super2@anchorstone.test", "super_admin").email)
    cr = _submit(superadmin, {"role_code": "risk_audit", "active": True}, "rbac.set_role_active")
    assert super2.post(f"/api/v1/change-requests/{cr['id']}/approve").status_code == 200
    assert Role.query.filter_by(code="risk_audit").one().active

    cr = _submit(superadmin, {"user_id": users["staff"].id, "branch_ids": [1]}, "rbac.set_branch_scope")
    assert json.loads(json.dumps(cr["payload"])) == {"user_id": users["staff"].id, "all_branches": False, "branch_ids": [1]}
    assert super2.post(f"/api/v1/change-requests/{cr['id']}/approve").status_code == 200
    _submit(superadmin, {"user_id": users["staff"].id, "branch_ids": [99]}, "rbac.set_branch_scope", expect=400)


def test_limit_must_be_for_an_amount_limited_permission(users, superadmin):
    _submit(superadmin, {"subject_type": "user", "user_id": users["staff"].id, "permission": "deposit.record",
                         "max_per_item": "10"}, "rbac.set_limit", expect=400)
    _submit(superadmin, {"subject_type": "user", "user_id": users["staff"].id, "permission": "withdrawal.approve",
                         "max_per_item": "10.001"}, "rbac.set_limit", expect=400)
