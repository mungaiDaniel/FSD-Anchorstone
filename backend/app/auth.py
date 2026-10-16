"""
Server-side role enforcement.

Every protected endpoint uses one of:

    @staff_required        any active staff account (role user/admin/super_admin)
    @admin_required        admin or super_admin
    @super_admin_required  super_admin only

The role is read from the database on every request — never trusted from the
JWT claims — so a deactivated or demoted user loses access immediately rather
than when their token expires.

An account still on a temporary password (must_change_password) is refused
everywhere with code PASSWORD_CHANGE_REQUIRED, except on endpoints marked
@password_change_endpoint (changing the password, reading /me).
"""
import functools

from flask import g
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
from sqlalchemy import func

from app.Admin.model import ROLE_LEVELS, User
from app.utils.http import error

PASSWORD_CHANGE_REQUIRED = "PASSWORD_CHANGE_REQUIRED"


def roles_required(min_role: str, *, allow_temporary_password: bool = False):
    min_level = ROLE_LEVELS[min_role]

    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            verify_jwt_in_request()
            identity = get_jwt_identity()
            if not isinstance(identity, str) or not identity.strip():
                return error("Invalid session. Please sign in again.", 401)

            user = User.query.filter(func.lower(User.email) == identity.strip().lower()).first()
            if user is None:
                return error("Invalid session. Please sign in again.", 401)
            if user.status != "active":
                return error("This account has been disabled.", 401)
            if user.must_change_password and not allow_temporary_password:
                return error("You must set a new password before continuing.", 403, code=PASSWORD_CHANGE_REQUIRED)
            if user.role_level < min_level:
                return error("You do not have permission to perform this action.", 403)

            g.current_user = user
            return fn(*args, **kwargs)

        return wrapper

    return decorator


password_change_endpoint = roles_required("user", allow_temporary_password=True)
staff_required = roles_required("user")
admin_required = roles_required("admin")
super_admin_required = roles_required("super_admin")


def current_user() -> User:
    return g.current_user


def actor_email() -> str:
    return g.current_user.email
