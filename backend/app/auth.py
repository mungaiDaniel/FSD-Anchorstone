"""
Server-side permission enforcement.

Every protected endpoint uses one of:

    @requires("withdrawal.approve")   an active account holding that permission
    @password_change_endpoint         any active account, even on a temporary password

Permissions come from roles (app/Access): the user's primary built-in role
(user.role) plus any extra roles. The user, their status and their roles are
read from the database on every request — never trusted from the JWT claims —
so a disabled user or a revoked role loses access immediately rather than when
the token expires.

The three built-in roles reproduce the old rules exactly:
    user (Operations staff) ⊂ admin (Operations admin) ⊂ super_admin (System administrator)

An account still on a temporary password (must_change_password) is refused
everywhere with code PASSWORD_CHANGE_REQUIRED, except on endpoints marked
@password_change_endpoint (changing the password, reading /me).

@staff_required / @admin_required / @super_admin_required are the old
role-level decorators, kept for one phase as aliases; routes use @requires.
"""
import functools

from flask import g
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
from sqlalchemy import func

from app.Admin.model import ROLE_LEVELS, User
from app.utils.http import Forbidden, error

PASSWORD_CHANGE_REQUIRED = "PASSWORD_CHANGE_REQUIRED"
NO_PERMISSION = "You do not have permission to perform this action."


def _authenticate(allow_temporary_password: bool):
    """Load the signed-in user from the DB. Returns (user, None) or (None, error_response)."""
    verify_jwt_in_request()
    identity = get_jwt_identity()
    if not isinstance(identity, str) or not identity.strip():
        return None, error("Invalid session. Please sign in again.", 401)

    user = User.query.filter(func.lower(User.email) == identity.strip().lower()).first()
    if user is None:
        return None, error("Invalid session. Please sign in again.", 401)
    if user.status != "active":
        return None, error("This account has been disabled.", 401)
    if user.must_change_password and not allow_temporary_password:
        return None, error("You must set a new password before continuing.", 403, code=PASSWORD_CHANGE_REQUIRED)
    return user, None


def requires(*permissions: str, allow_temporary_password: bool = False):
    """Require every listed permission (none = any active, signed-in account)."""

    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            user, failure = _authenticate(allow_temporary_password)
            if failure is not None:
                return failure
            g.current_user = user
            g.pop("permissions", None)
            held = user_permissions()
            if any(p not in held for p in permissions):
                g.pop("current_user", None)
                return error(NO_PERMISSION, 403)
            return fn(*args, **kwargs)

        wrapper.required_permissions = tuple(permissions)
        wrapper.allows_temporary_password = allow_temporary_password
        return wrapper

    return decorator


def roles_required(min_role: str, *, allow_temporary_password: bool = False):
    """Deprecated role-level check, kept as an alias for one phase."""
    min_level = ROLE_LEVELS[min_role]

    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            user, failure = _authenticate(allow_temporary_password)
            if failure is not None:
                return failure
            if user.role_level < min_level:
                return error(NO_PERMISSION, 403)
            g.current_user = user
            g.pop("permissions", None)
            return fn(*args, **kwargs)

        wrapper.required_role = min_role
        return wrapper

    return decorator


password_change_endpoint = requires(allow_temporary_password=True)
staff_required = roles_required("user")
admin_required = roles_required("admin")
super_admin_required = roles_required("super_admin")


def current_user() -> User:
    return g.current_user


def actor_email() -> str:
    return g.current_user.email


def user_permissions() -> frozenset[str]:
    """The signed-in user's permissions, loaded once per request."""
    from app.Access.service import permissions_for

    if "permissions" not in g:
        g.permissions = permissions_for(g.current_user)
    return g.permissions


def has_permission(permission: str) -> bool:
    return permission in user_permissions()


def require_permission(permission: str, message: str = NO_PERMISSION) -> None:
    """For checks that depend on the request (e.g. which report is exported)."""
    if not has_permission(permission):
        raise Forbidden(message)
