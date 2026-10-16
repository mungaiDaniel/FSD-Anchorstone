from datetime import timedelta

import pytest

from app.Admin.model import AccountLockout, LoginAttempt
from app.database.database import db
from app.utils.audit_log import AuditLog
from app.utils.dates import utcnow

STAFF = "staff@anchorstone.test"


@pytest.fixture
def clock(monkeypatch):
    """Controllable 'now' for the sign-in limits."""
    import app.Admin.route as route
    import app.Admin.service as service

    state = {"now": utcnow()}

    def now():
        return state["now"]

    monkeypatch.setattr(route, "utcnow", now)
    monkeypatch.setattr(service, "utcnow", now)

    def advance(minutes):
        state["now"] += timedelta(minutes=minutes)

    return advance


def login(client, email, password, ip="10.0.0.1", **headers):
    return client.post("/api/v1/login", json={"email": email, "password": password},
                       environ_overrides={"REMOTE_ADDR": ip}, headers=headers)


def actions(name):
    return AuditLog.query.filter(AuditLog.action == name).all()


def test_five_failures_lock_the_account_even_for_the_right_password(client, users, clock):
    for _ in range(4):
        assert login(client, STAFF, "wrong-password").status_code == 401
    fifth = login(client, STAFF, "wrong-password")
    assert fifth.status_code == 429 and fifth.get_json()["code"] == "ACCOUNT_LOCKED"

    refused = login(client, STAFF, "password123")
    assert refused.status_code == 429 and refused.get_json()["code"] == "ACCOUNT_LOCKED"

    assert len(actions("LOGIN_FAILED")) == 5
    locked = actions("ACCOUNT_LOCKED")
    assert len(locked) == 1 and locked[0].target_name == STAFF and locked[0].user_id == users["staff"].id
    # Counters live in the database, not in worker memory.
    assert LoginAttempt.query.filter_by(email=STAFF, outcome="failed").count() == 5
    assert LoginAttempt.query.filter_by(email=STAFF, outcome="blocked").count() == 1


def test_lock_expires_after_fifteen_minutes(client, users, clock):
    for _ in range(5):
        login(client, STAFF, "wrong-password")
    clock(14)
    assert login(client, STAFF, "password123").status_code == 429
    clock(2)
    assert login(client, STAFF, "password123").status_code == 200


def test_only_failures_within_fifteen_minutes_count(client, users, clock):
    for _ in range(4):
        login(client, STAFF, "wrong-password")
    clock(16)
    assert login(client, STAFF, "wrong-password").status_code == 401  # only 1 in the window
    assert login(client, STAFF, "password123").status_code == 200


def test_successful_sign_in_resets_the_count(client, users, clock):
    for _ in range(4):
        login(client, STAFF, "wrong-password")
    assert login(client, STAFF, "password123").status_code == 200
    for _ in range(4):
        assert login(client, STAFF, "wrong-password").status_code == 401
    assert login(client, STAFF, "password123").status_code == 200


def test_unknown_email_locks_the_same_way(client, users, clock):
    """A lockout must not reveal which emails have accounts."""
    real = [login(client, STAFF, "wrong-password") for _ in range(6)]
    fake = [login(client, "nobody@anchorstone.test", "wrong-password") for _ in range(6)]
    assert [r.status_code for r in real] == [r.status_code for r in fake] == [401] * 4 + [429] * 2
    assert [r.get_json()["message"] for r in real] == [r.get_json()["message"] for r in fake]


def test_admin_can_unlock_and_users_list_shows_the_lock(client, users, clock, admin1, staff, superadmin):
    for _ in range(5):
        login(client, STAFF, "wrong-password")
    listed = {u["email"]: u for u in superadmin.get("/api/v1/users").get_json()["data"]}
    assert listed[STAFF]["locked_until"] is not None
    assert listed["admin1@anchorstone.test"]["locked_until"] is None

    uid = users["staff"].id
    assert staff.post(f"/api/v1/users/{uid}/unlock").status_code == 403  # staff can't unlock
    assert admin1.post(f"/api/v1/users/{uid}/unlock").status_code == 200
    assert actions("UNLOCK_ACCOUNT")[0].user_email == "admin1@anchorstone.test"
    assert login(client, STAFF, "password123").status_code == 200

    # Unlocking starts the count afresh, and an unlocked account can't be "unlocked" again.
    assert admin1.post(f"/api/v1/users/{uid}/unlock").status_code == 409
    for _ in range(4):
        assert login(client, STAFF, "wrong-password").status_code == 401


def test_per_ip_limit_blocks_the_ip_not_other_addresses(client, users, clock):
    for i in range(20):
        login(client, f"guess{i}@anchorstone.test", "wrong-password", ip="203.0.113.9")
    blocked = login(client, STAFF, "password123", ip="203.0.113.9")
    assert blocked.status_code == 429 and blocked.get_json()["code"] == "LOGIN_RATE_LIMITED"
    assert len(actions("LOGIN_IP_RATE_LIMITED")) == 1

    assert login(client, STAFF, "password123", ip="198.51.100.4").status_code == 200
    clock(16)
    assert login(client, STAFF, "password123", ip="203.0.113.9").status_code == 200


def test_spoofed_forwarded_for_does_not_dodge_the_ip_limit(client, users, clock):
    for i in range(20):
        login(client, f"guess{i}@anchorstone.test", "wrong-password", ip="203.0.113.9",
              **{"X-Forwarded-For": f"192.0.2.{i}"})
    res = login(client, STAFF, "password123", ip="203.0.113.9", **{"X-Forwarded-For": "192.0.2.200"})
    assert res.status_code == 429
    assert {a.ip_address for a in LoginAttempt.query.all()} == {"203.0.113.9"}


def test_lockouts_are_stored_by_email(client, users, clock):
    for _ in range(5):
        login(client, "STAFF@anchorstone.test", "wrong-password")
    assert db.session.get(AccountLockout, STAFF).locked_until is not None
