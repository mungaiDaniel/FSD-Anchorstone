from datetime import datetime, timezone

from flask_jwt_extended import create_access_token
from passlib.handlers.md5_crypt import md5_crypt
from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, Index, Integer, String, true
from werkzeug.security import check_password_hash as wz_check_password_hash
from werkzeug.security import generate_password_hash as wz_generate_password_hash

from app.database.database import db
from base_model import Base

# Staff roles, lowest to highest. "user" is ordinary staff (records deposits and
# withdrawal requests); "admin" is the checker (approves withdrawals and interest
# periods); "super_admin" also manages users, audit log, backups and settings.
ROLE_LEVELS = {"user": 0, "admin": 1, "super_admin": 2}
# Accounts are only created by a super admin (no public sign-up). "disabled"
# blocks sign-in without deleting the account or its audit history.
USER_STATUSES = ("active", "disabled")


class User(Base, db.Model):
    __tablename__ = "user"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'admin', 'super_admin')", name="ck_user_role"),
        CheckConstraint("status IN ('active', 'disabled')", name="ck_user_status"),
    )

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    email = Column(String(100), unique=True, nullable=False)
    password = Column(String(1000), nullable=False)
    role = Column(String(20), nullable=False, default="user", server_default="user")
    status = Column(String(20), nullable=False, default="active", server_default="active")
    # Set when a super admin creates the account or resets its password (the
    # password is a temporary one they've seen). Until the user picks their own,
    # every endpoint except the password change refuses them (see app/auth.py).
    must_change_password = Column(Boolean, nullable=False, default=True, server_default=true())
    password_changed_at = Column(DateTime(timezone=True), nullable=True)
    created = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    @property
    def role_level(self) -> int:
        return ROLE_LEVELS.get(self.role, 0)

    def generate_auth_token(self) -> str:
        # Claims are informational for the frontend only; every request re-reads
        # the user's current role/status from the database (see app/auth.py), so
        # a demotion or deactivation takes effect immediately.
        return create_access_token(identity=self.email, additional_claims={"role": self.role})

    @staticmethod
    def generate_password_hash(password: str) -> str:
        return wz_generate_password_hash(password)

    def verify_password_hash(self, password: str) -> bool:
        if not password or not self.password:
            return False
        try:
            if wz_check_password_hash(self.password, password):
                return True
        except (ValueError, TypeError):
            pass
        # Legacy md5_crypt hashes (accounts migrated from older systems).
        try:
            return md5_crypt.verify(password, self.password)
        except (ValueError, TypeError):
            return False

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "role": self.role,
            "status": self.status,
            "must_change_password": self.must_change_password,
            "password_changed_at": self.password_changed_at.isoformat() if self.password_changed_at else None,
            "created": self.created.isoformat() if self.created else None,
        }


class LoginAttempt(Base, db.Model):
    """Every sign-in attempt, kept in the database so the limits hold across
    gunicorn workers. outcome: success | failed (wrong email or password) |
    blocked (refused by a lockout or the per-IP limit, password not checked)."""

    __tablename__ = "login_attempts"
    __table_args__ = (
        CheckConstraint("outcome IN ('success', 'failed', 'blocked')", name="ck_login_attempts_outcome"),
        Index("ix_login_attempts_email_time", "email", "attempted_at"),
        Index("ix_login_attempts_ip_time", "ip_address", "attempted_at"),
    )

    id = Column(Integer, primary_key=True)
    email = Column(String(150), nullable=False)  # as typed, lower-cased; may not be an account
    ip_address = Column(String(45), nullable=False)
    outcome = Column(String(10), nullable=False)
    attempted_at = Column(DateTime(timezone=True), nullable=False)


class AccountLockout(Base, db.Model):
    """Per-email lockout. Keyed by the email typed, not the user id, so an
    unknown email locks exactly like a real one and the login form can't be
    used to discover which emails have accounts.

    Failures are counted only after counting_from, which moves forward when an
    account locks or an admin unlocks it, so each lock needs 5 fresh failures."""

    __tablename__ = "account_lockouts"

    email = Column(String(150), primary_key=True)
    locked_until = Column(DateTime(timezone=True), nullable=True)
    counting_from = Column(DateTime(timezone=True), nullable=True)
    unlocked_by = Column(String(120), nullable=True)
