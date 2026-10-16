from app.Admin.model import User
from app.database.database import db


def test_unauthenticated_requests_are_rejected(client):
    for url in ("/api/v1/investors", "/api/v1/deposits", "/api/v1/stats/overview", "/api/v1/users"):
        assert client.get(url).status_code == 401, url


def test_login_does_not_reveal_whether_email_exists(client, users):
    unknown = client.post("/api/v1/login", json={"email": "nobody@x.test", "password": "password123"})
    wrong = client.post("/api/v1/login", json={"email": users["staff"].email, "password": "wrong-password"})
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.get_json()["message"] == wrong.get_json()["message"]


def test_login_success_returns_role(client, users):
    res = client.post("/api/v1/login", json={"email": "ADMIN1@anchorstone.test", "password": "password123"})
    assert res.status_code == 200
    assert res.get_json()["data"]["role"] == "admin"


def test_there_is_no_public_sign_up(client):
    res = client.post("/api/v1/users", json={"name": "New", "email": "new@x.test", "password": "password123"})
    assert res.status_code == 401


def test_only_super_admin_creates_accounts(admin1, staff):
    body = {"name": "New", "email": "new@x.test", "role": "user"}
    assert admin1.post("/api/v1/users", body).status_code == 403
    assert staff.post("/api/v1/users", body).status_code == 403


def test_new_account_must_change_temporary_password_first(client, superadmin):
    res = superadmin.post("/api/v1/users", {"name": "Wanjiku", "email": "Wanjiku@anchorstone.test", "role": "admin"})
    assert res.status_code == 201
    data = res.get_json()["data"]
    temp = data["temporary_password"]
    assert data["user"]["must_change_password"] is True and data["user"]["role"] == "admin"
    assert len(temp) >= 12

    login = client.post("/api/v1/login", json={"email": "wanjiku@anchorstone.test", "password": temp})
    assert login.status_code == 200
    assert login.get_json()["data"]["must_change_password"] is True
    headers = {"Authorization": f"Bearer {login.get_json()['data']['access_token']}"}

    # Locked out of everything except /me and changing the password.
    blocked = client.get("/api/v1/investors", headers=headers)
    assert blocked.status_code == 403 and blocked.get_json()["code"] == "PASSWORD_CHANGE_REQUIRED"
    assert client.get("/api/v1/me", headers=headers).status_code == 200

    def change(current, new):
        return client.post("/api/v1/me/password", json={"current_password": current, "new_password": new}, headers=headers)

    assert change("wrong-password", "BrandNew2026").status_code == 400
    assert change(temp, "short1").status_code == 400                # too short
    assert change(temp, "onlyletterslong").status_code == 400       # no digits
    assert change(temp, temp).status_code == 400                    # same as current
    assert change(temp, "BrandNew2026").status_code == 200

    assert client.get("/api/v1/investors", headers=headers).status_code == 200
    relog = client.post("/api/v1/login", json={"email": "wanjiku@anchorstone.test", "password": "BrandNew2026"})
    assert relog.get_json()["data"]["must_change_password"] is False


def test_password_reset_issues_temporary_password(client, superadmin, users):
    res = superadmin.post(f"/api/v1/users/{users['staff'].id}/reset-password")
    assert res.status_code == 200
    temp = res.get_json()["data"]["temporary_password"]
    assert client.post("/api/v1/login", json={"email": users["staff"].email, "password": "password123"}).status_code == 401
    login = client.post("/api/v1/login", json={"email": users["staff"].email, "password": temp})
    assert login.get_json()["data"]["must_change_password"] is True


def test_disabled_account_cannot_sign_in(client, superadmin, users):
    assert superadmin.patch(f"/api/v1/users/{users['staff'].id}/status", {"status": "disabled"}).status_code == 200
    res = client.post("/api/v1/login", json={"email": users["staff"].email, "password": "password123"})
    assert res.status_code == 403


def test_staff_cannot_use_admin_or_super_admin_endpoints(staff, admin1):
    assert staff.post("/api/v1/interest/rates", {"rate_percent": "10", "effective_from": "2026-01-01"}).status_code == 403
    assert staff.post("/api/v1/withdrawals/1/approve").status_code == 403
    assert staff.post("/api/v1/deposits/1/reverse", {"reason": "x"}).status_code == 403
    assert staff.get("/api/v1/users").status_code == 403
    assert admin1.get("/api/v1/users").status_code == 403
    assert staff.get("/api/v1/audit-logs").status_code == 403
    assert admin1.get("/api/v1/audit-logs").status_code == 200  # admins may view the audit log


def test_role_is_read_from_database_not_token(staff, users):
    """A token issued while active stops working as soon as the account is deactivated."""
    assert staff.get("/api/v1/investors").status_code == 200
    users["staff"].status = "disabled"
    db.session.commit()
    assert staff.get("/api/v1/investors").status_code == 401


def test_super_admin_manages_users_but_not_own_account(superadmin, users):
    res = superadmin.patch(f"/api/v1/users/{users['staff'].id}/role", {"role": "admin"})
    assert res.status_code == 200
    assert db.session.get(User, users["staff"].id).role == "admin"

    assert superadmin.patch(f"/api/v1/users/{users['super'].id}/role", {"role": "user"}).status_code == 400
    assert superadmin.delete(f"/api/v1/users/{users['super'].id}").status_code == 400
