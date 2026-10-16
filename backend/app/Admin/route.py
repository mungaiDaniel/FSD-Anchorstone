"""
Staff accounts. There is no public sign-up: a super admin creates every
account and is shown a one-time temporary password to hand over. The new user
must replace it at first sign-in before anything else is reachable (enforced
in app/auth.py). Password resets work the same way.
"""
import secrets

from flask import Blueprint, current_app, request
from sqlalchemy import func

from app.Admin import service as login_protection
from app.Access.service import branch_scope
from app.Admin.model import ROLE_LEVELS, USER_STATUSES, User
from app.auth import actor_email, current_user, password_change_endpoint, requires, user_permissions
from app.database.database import db
from app.utils.audit_log import create_audit_log, get_client_ip
from app.utils.dates import iso, utcnow
from app.utils.http import Conflict, NotFound, ValidationError, error, ok

user_v1 = Blueprint("user_v1", __name__)

MIN_PASSWORD_LENGTH = 10
# No look-alike characters (0/O, 1/l/I) — temporary passwords are read aloud or copied by hand.
_TEMP_ALPHABET = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def generate_temporary_password() -> str:
    groups = ["".join(secrets.choice(_TEMP_ALPHABET) for _ in range(4)) for _ in range(3)]
    return "-".join(groups)  # e.g. "Kp7w-Xq3m-Rt9z"


def validate_new_password(password, *, email: str, current_hash_user: User | None = None) -> str:
    if not isinstance(password, str) or len(password) < MIN_PASSWORD_LENGTH:
        raise ValidationError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    if password.strip() != password:
        raise ValidationError("Password can't start or end with a space.")
    if password.lower() == email.lower():
        raise ValidationError("Password can't be your email address.")
    if not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
        raise ValidationError("Password must contain both letters and numbers.")
    if current_hash_user is not None and current_hash_user.verify_password_hash(password):
        raise ValidationError("Choose a password different from your current one.")
    return password


def _get_user(user_id: int) -> User:
    user = db.session.get(User, user_id)
    if user is None:
        raise NotFound("User not found.")
    return user


def _guard_self(user: User, action: str) -> None:
    if user.id == current_user().id:
        raise ValidationError(f"You cannot {action} your own account.")


# ── Sign-in and own account ──────────────────────────────────────────────


@user_v1.post("/api/v1/login")
def login():
    data = request.get_json(silent=True) or {}
    email = str(data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    if not email or not password:
        raise ValidationError("Email and password are required.")

    now, ip = utcnow(), get_client_ip()
    login_protection.serialize(email)
    refused = login_protection.refusal(email, ip, now)
    if refused is not None:
        login_protection.record_blocked(email, ip, now)
        db.session.commit()
        code, message = refused
        return error(message, 429, code=code)

    user = User.query.filter(func.lower(User.email) == email).first()
    # Same response for unknown email and wrong password, so the login form
    # can't be used to discover which emails have accounts.
    if user is None or not user.verify_password_hash(password):
        locked = login_protection.record_failure(email, ip, user, now)
        db.session.commit()
        if locked:
            return error(login_protection.ACCOUNT_LOCKED_MESSAGE.format(
                minutes=current_app.config["LOGIN_LOCK_MINUTES"]), 429, code="ACCOUNT_LOCKED")
        return error("Invalid email or password.", 401)

    login_protection.record_success(email, ip, now)
    db.session.commit()
    if user.status != "active":
        return error("This account has been disabled. Contact your administrator.", 403)

    return ok({
        "access_token": user.generate_auth_token(),
        "role": user.role,
        "name": user.name,
        "email": user.email,
        "must_change_password": user.must_change_password,
    }, "Signed in.")


@user_v1.get("/api/v1/me")
@password_change_endpoint
def me():
    user = current_user()
    scope = branch_scope(user)
    return ok({**user.to_dict(), "permissions": sorted(user_permissions()),
               "branch_scope": None if scope is None else sorted(scope)})


@user_v1.post("/api/v1/me/password")
@password_change_endpoint
def change_own_password():
    data = request.get_json(silent=True) or {}
    user = current_user()
    if not user.verify_password_hash(data.get("current_password") or ""):
        raise ValidationError("Your current password is incorrect.")
    new_password = validate_new_password(data.get("new_password"), email=user.email, current_hash_user=user)

    was_temporary = user.must_change_password
    user.password = User.generate_password_hash(new_password)
    user.must_change_password = False
    user.password_changed_at = utcnow()
    create_audit_log("CHANGE_OWN_PASSWORD", target_type="user", target_id=user.id, target_name=user.email,
                     description="Replaced temporary password" if was_temporary else None)
    db.session.commit()
    return ok(user.to_dict(), "Password changed.")


# ── User management (super admin) ───────────────────────────────────────


@user_v1.get("/api/v1/users")
@requires("user.manage")
def list_users():
    users = User.query.order_by(User.created.desc()).all()
    locked = login_protection.locked_until_by_email([u.email.lower() for u in users])
    return ok([{**u.to_dict(), "locked_until": iso(locked.get(u.email.lower()))} for u in users])


@user_v1.post("/api/v1/users")
@requires("user.manage")
def create_user():
    data = request.get_json(silent=True) or {}
    name = str(data.get("name") or "").strip()
    email = str(data.get("email") or "").strip().lower()
    role = data.get("role") or "user"

    if not name:
        raise ValidationError("Name is required.")
    if len(name) > 100 or len(email) > 100:
        raise ValidationError("Name and email must be at most 100 characters.")
    if not email or "@" not in email or "." not in email.split("@")[-1]:
        raise ValidationError("A valid email is required.")
    if role not in ROLE_LEVELS:
        raise ValidationError(f"role must be one of: {', '.join(ROLE_LEVELS)}.")
    if db.session.query(User.id).filter(func.lower(User.email) == email).first():
        raise Conflict("An account with that email already exists.")

    temporary_password = generate_temporary_password()
    user = User(name=name, email=email, password=User.generate_password_hash(temporary_password),
                role=role, status="active", must_change_password=True)
    db.session.add(user)
    db.session.flush()
    create_audit_log("CREATE_USER", target_type="user", target_id=user.id, target_name=email,
                     new_value={"name": name, "role": role})
    db.session.commit()
    # The temporary password is returned exactly once and never stored in plain text.
    return ok({"user": user.to_dict(), "temporary_password": temporary_password},
              f"Account created for {email}.", 201)


@user_v1.get("/api/v1/users/<int:user_id>")
@requires("user.manage")
def get_user(user_id):
    return ok(_get_user(user_id).to_dict())


@user_v1.patch("/api/v1/users/<int:user_id>/status")
@requires("user.manage")
def set_user_status(user_id):
    status = (request.get_json(silent=True) or {}).get("status")
    if status not in USER_STATUSES:
        raise ValidationError(f"status must be one of: {', '.join(USER_STATUSES)}.")
    user = _get_user(user_id)
    _guard_self(user, "change the status of")
    old = user.status
    user.status = status
    create_audit_log("SET_USER_STATUS", target_type="user", target_id=user.id, target_name=user.email,
                     old_value={"status": old}, new_value={"status": status})
    db.session.commit()
    return ok(user.to_dict(), "Account enabled." if status == "active" else "Account disabled.")


@user_v1.patch("/api/v1/users/<int:user_id>/role")
@requires("user.manage")
def set_user_role(user_id):
    role = (request.get_json(silent=True) or {}).get("role")
    if role not in ROLE_LEVELS:
        raise ValidationError(f"role must be one of: {', '.join(ROLE_LEVELS)}.")
    user = _get_user(user_id)
    _guard_self(user, "change the role of")
    old = user.role
    user.role = role
    create_audit_log("SET_USER_ROLE", target_type="user", target_id=user.id, target_name=user.email,
                     old_value={"role": old}, new_value={"role": role})
    db.session.commit()
    return ok(user.to_dict(), "Role updated.")


@user_v1.post("/api/v1/users/<int:user_id>/reset-password")
@requires("user.manage")
def reset_password(user_id):
    user = _get_user(user_id)
    _guard_self(user, "reset the password of")  # use Settings -> Change password instead
    temporary_password = generate_temporary_password()
    user.password = User.generate_password_hash(temporary_password)
    user.must_change_password = True
    create_audit_log("RESET_PASSWORD", target_type="user", target_id=user.id, target_name=user.email)
    db.session.commit()
    return ok({"user": user.to_dict(), "temporary_password": temporary_password},
              f"Password reset for {user.email}.")


@user_v1.post("/api/v1/users/<int:user_id>/unlock")
@requires("user.unlock")
def unlock_account(user_id):
    """Lift a sign-in lockout early (admins and super admins)."""
    user = _get_user(user_id)
    login_protection.unlock(user, actor_email())
    return ok({**user.to_dict(), "locked_until": None}, f"{user.email} can sign in again.")


@user_v1.delete("/api/v1/users/<int:user_id>")
@requires("user.manage")
def delete_user(user_id):
    user = _get_user(user_id)
    _guard_self(user, "delete")
    email = user.email
    db.session.delete(user)
    create_audit_log("DELETE_USER", target_type="user", target_id=user_id, target_name=email)
    db.session.commit()
    return ok(message="User deleted.")
