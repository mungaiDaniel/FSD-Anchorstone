"""
Sign-in protection. The counters live in PostgreSQL (login_attempts,
account_lockouts), so every gunicorn worker sees the same numbers.

  Per account  LOGIN_MAX_FAILURES failed attempts for one email within
               LOGIN_WINDOW_MINUTES lock that email for LOGIN_LOCK_MINUTES.
               While locked, even the right password is refused. An admin can
               unlock early.
  Per IP       LOGIN_IP_MAX_FAILURES failed attempts from one IP within
               LOGIN_WINDOW_MINUTES refuse every sign-in from that IP until
               the oldest of them leaves the window.

Lockouts are keyed by the email as typed, so an unknown email behaves exactly
like a real one and the form can't reveal which emails have accounts.
Concurrent attempts for the same email are serialized with a transaction-level
advisory lock, so parallel requests can't slip past the limit.
"""
from datetime import datetime, timedelta

from sqlalchemy import func, text

from app.Admin.model import AccountLockout, LoginAttempt, User
from app.database.database import db
from app.Settings import business as settings
from app.utils.audit_log import create_audit_log
from app.utils.dates import utcnow
from app.utils.http import Conflict

ACCOUNT_LOCKED_MESSAGE = (
    "Too many failed sign-in attempts. This account is locked for {minutes} minutes. "
    "Try again later or ask an administrator to unlock it."
)
IP_LIMITED_MESSAGE = "Too many failed sign-in attempts from your network. Try again in a few minutes."


# The limits are business-rule settings (app/Settings/registry.py), changed under maker-checker.
_KEYS = {
    "LOGIN_MAX_FAILURES": "security.login_max_failures",
    "LOGIN_WINDOW_MINUTES": "security.login_window_minutes",
    "LOGIN_LOCK_MINUTES": "security.login_lock_minutes",
    "LOGIN_IP_MAX_FAILURES": "security.login_ip_max_failures",
}


def _setting(name: str) -> int:
    return int(settings.get(_KEYS[name]))


def serialize(email: str) -> None:
    """Hold a per-email advisory lock until the current transaction ends."""
    db.session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": f"login:{email}"})


def _lockout(email: str) -> AccountLockout | None:
    return db.session.get(AccountLockout, email)


def _record(email: str, ip: str, outcome: str, now: datetime) -> None:
    db.session.add(LoginAttempt(email=email, ip_address=ip, outcome=outcome, attempted_at=now))


def _ip_failures(ip: str, now: datetime) -> int:
    since = now - timedelta(minutes=_setting("LOGIN_WINDOW_MINUTES"))
    return (
        db.session.query(func.count(LoginAttempt.id))
        .filter(LoginAttempt.ip_address == ip, LoginAttempt.outcome == "failed", LoginAttempt.attempted_at > since)
        .scalar()
    )


def _email_failures(email: str, now: datetime) -> int:
    since = now - timedelta(minutes=_setting("LOGIN_WINDOW_MINUTES"))
    lockout = _lockout(email)
    if lockout is not None and lockout.counting_from is not None:
        since = max(since, lockout.counting_from)
    last_success = (
        db.session.query(func.max(LoginAttempt.attempted_at))
        .filter(LoginAttempt.email == email, LoginAttempt.outcome == "success")
        .scalar()
    )
    if last_success is not None:
        since = max(since, last_success)
    return (
        db.session.query(func.count(LoginAttempt.id))
        .filter(LoginAttempt.email == email, LoginAttempt.outcome == "failed", LoginAttempt.attempted_at > since)
        .scalar()
    )


def refusal(email: str, ip: str, now: datetime) -> tuple[str, str] | None:
    """(code, message) if this attempt must be refused without checking the password."""
    lockout = _lockout(email)
    if lockout is not None and lockout.locked_until is not None and lockout.locked_until > now:
        return "ACCOUNT_LOCKED", ACCOUNT_LOCKED_MESSAGE.format(minutes=_setting("LOGIN_LOCK_MINUTES"))
    if _ip_failures(ip, now) >= _setting("LOGIN_IP_MAX_FAILURES"):
        return "LOGIN_RATE_LIMITED", IP_LIMITED_MESSAGE
    return None


def record_blocked(email: str, ip: str, now: datetime) -> None:
    _record(email, ip, "blocked", now)


def record_success(email: str, ip: str, now: datetime) -> None:
    _record(email, ip, "success", now)


def record_failure(email: str, ip: str, user: User | None, now: datetime) -> bool:
    """Log a wrong email/password and apply the limits. Returns True if this
    failure locked the account. Counting happens before any audit write, while
    the advisory lock is held. The caller commits."""
    _record(email, ip, "failed", now)
    db.session.flush()
    window, max_failures = _setting("LOGIN_WINDOW_MINUTES"), _setting("LOGIN_MAX_FAILURES")
    ip_failures = _ip_failures(ip, now)
    locks = _email_failures(email, now) >= max_failures
    minutes = _setting("LOGIN_LOCK_MINUTES")
    if locks:
        lockout = _lockout(email) or AccountLockout(email=email)
        lockout.locked_until = now + timedelta(minutes=minutes)
        lockout.counting_from = now
        lockout.unlocked_by = None
        db.session.add(lockout)

    actor = {"actor_user_id": user.id if user else None, "actor_user_email": email,
             "actor_user_name": user.name if user else None}
    target = {"target_type": "user", "target_id": user.id if user else None, "target_name": email}
    create_audit_log("LOGIN_FAILED", description="Wrong password" if user else "Wrong email or password",
                     **target, **actor)
    if ip_failures == _setting("LOGIN_IP_MAX_FAILURES"):
        create_audit_log("LOGIN_IP_RATE_LIMITED", target_type="ip_address", target_name=ip,
                         description=f"{ip_failures} failed sign-ins from {ip} within {window} minutes; "
                                     "sign-ins from it are paused", **actor)
    if locks:
        create_audit_log("ACCOUNT_LOCKED", description=f"Locked for {minutes} minutes after {max_failures} "
                                                       f"failed sign-ins within {window} minutes",
                         new_value={"locked_until": (now + timedelta(minutes=minutes)).isoformat()},
                         **target, **actor)
    return locks


def locked_until_by_email(emails: list[str]) -> dict[str, datetime]:
    """Current lock expiry for each of these (lower-cased) emails that is locked now."""
    if not emails:
        return {}
    now = utcnow()
    rows = AccountLockout.query.filter(AccountLockout.email.in_(emails), AccountLockout.locked_until > now).all()
    return {r.email: r.locked_until for r in rows}


def unlock(user: User, actor: str) -> None:
    email = user.email.lower()
    now = utcnow()
    lockout = _lockout(email)
    if lockout is None or lockout.locked_until is None or lockout.locked_until <= now:
        raise Conflict("This account isn't locked.")
    old = lockout.locked_until.isoformat()
    lockout.locked_until = None
    lockout.counting_from = now  # earlier failures no longer count towards the next lock
    lockout.unlocked_by = actor
    create_audit_log("UNLOCK_ACCOUNT", target_type="user", target_id=user.id, target_name=email,
                     old_value={"locked_until": old}, new_value={"locked_until": None})
    db.session.commit()
