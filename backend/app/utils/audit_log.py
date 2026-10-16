"""
Insert-only audit trail for compliance.

Usage (after the business change has been committed):
    create_audit_log("APPROVE_WITHDRAWAL", target_type="withdrawal", target_id=w.id,
                     target_name=investor.client_code, new_value={...})

create_audit_log commits its own row, so call it after the main transaction
commits — never in the middle of one.
"""

from datetime import datetime, timezone
from flask import request, g, has_request_context
from app.database.database import db
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, func
from base_model import Base
import json
from typing import Any, Optional


class AuditLog(Base, db.Model):
    """
    Insert-only audit log table for compliance and security tracking.
    Logs all significant actions including file uploads, toggles, and email notifications.
    """
    __tablename__ = 'audit_logs'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=True, index=True)  # NULL for anonymous actions
    user_email = Column(String(120), nullable=True, index=True)
    user_name = Column(String(120), nullable=True, index=True)
    action = Column(String(100), nullable=False, index=True)  # UPLOAD_FILE, TOGGLE_ACTIVE, SEND_EMAIL, etc.
    target_type = Column(String(50), nullable=True)  # 'investor', 'deposit', 'withdrawal', 'interest_period', ...
    target_id = Column(Integer, nullable=True, index=True)  # FK to the affected resource
    target_name = Column(String(255), nullable=True)  # Human-readable identifier (batch_name, investor_name)
    description = Column(Text, nullable=True)  # Additional context (e.g., "Excel file with 50 rows")
    old_value = Column(Text, nullable=True)  # Previous state (JSON serialized)
    new_value = Column(Text, nullable=True)  # New state (JSON serialized)
    ip_address = Column(String(45), nullable=True, index=True)  # IPv4 or IPv6
    user_agent = Column(String(500), nullable=True)  # Browser/client info
    timestamp = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    success = Column(Boolean, default=True)  # Whether action completed successfully
    error_message = Column(Text, nullable=True)  # Error details if success=False
    
    def __repr__(self):
        return f'<AuditLog {self.action} on {self.target_type}#{self.target_id} at {self.timestamp}>'
    
    def to_dict(self):
        """Serialize audit log to dictionary"""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'user_email': self.user_email,
            'user_name': self.user_name,
            'action': self.action,
            'target_type': self.target_type,
            'target_id': self.target_id,
            'target_name': self.target_name,
            'description': self.description,
            'old_value': self.old_value,
            'new_value': self.new_value,
            'ip_address': self.ip_address,
            'user_agent': self.user_agent,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'success': self.success,
            'error_message': self.error_message,
        }


def get_client_ip() -> str:
    """
    Extract client IP address from request, handling proxies.
    Respects X-Forwarded-For header for load-balanced environments.
    """
    if not has_request_context():
        return '127.0.0.1'

    if request.environ.get('HTTP_X_FORWARDED_FOR'):
        # X-Forwarded-For header (load balancer, proxy)
        return request.environ.get('HTTP_X_FORWARDED_FOR').split(',')[0].strip()
    return request.environ.get('REMOTE_ADDR', 'UNKNOWN')


def get_user_id() -> Optional[int]:
    """
    Extract user ID from JWT token or session.
    Returns None if no user is authenticated or if identity is not an integer.
    Note: JWT identity may be an email string depending on how the token was issued.
    The audit_logs.user_id column is an Integer, so we only return valid int values.
    """
    if not has_request_context():
        return None
    try:
        from flask_jwt_extended import get_jwt_identity
        identity = get_jwt_identity()
        # Only accept true numeric identities.
        if isinstance(identity, int):
            return identity
        if isinstance(identity, str) and identity.isdigit():
            return int(identity)
        return None
    except Exception:
        return None


def get_user_identity_meta():
    """Return (user_id, user_email, user_name) from JWT identity when possible."""
    if not has_request_context():
        return None, None, None
    # Set by app.auth on every protected endpoint — no extra lookup needed.
    user = getattr(g, "current_user", None)
    if user is not None:
        return user.id, user.email, user.name
    try:
        from flask_jwt_extended import get_jwt_identity
        identity = get_jwt_identity()
    except Exception:
        return None, None, None

    # Legacy token payload: {"email": "..."}
    if isinstance(identity, dict):
        identity = identity.get("email")

    # Identity in this app is usually email string.
    if isinstance(identity, str) and identity.strip():
        normalized = identity.strip().lower()
        try:
            from app.Admin.model import User
            u = User.query.filter(func.lower(User.email) == normalized).first()
            if u:
                return u.id, u.email, u.name
            return None, normalized, None
        except Exception:
            return None, normalized, None

    # Fallback for numeric identity.
    if isinstance(identity, int):
        return identity, None, None

    return None, None, None


def create_audit_log(
    action: str,
    target_type: Optional[str] = None,
    target_id: Optional[int] = None,
    target_name: Optional[str] = None,
    description: Optional[str] = None,
    old_value: Optional[Any] = None,
    new_value: Optional[Any] = None,
    success: bool = True,
    error_message: Optional[str] = None,
    actor_user_id: Optional[int] = None,
    actor_user_email: Optional[str] = None,
    actor_user_name: Optional[str] = None,
) -> AuditLog:
    """
    Create and save an audit log entry.
    
    Args:
        action: Action type (e.g., 'UPLOAD_FILE', 'TOGGLE_ACTIVE', 'SEND_EMAIL')
        target_type: Resource type affected ('investor', 'deposit', 'withdrawal', ...)
        target_id: ID of the affected resource
        target_name: Human-readable name (batch_name, investor_name)
        description: Additional context about the action
        old_value: Previous state (will be JSON serialized)
        new_value: New state (will be JSON serialized)
        success: Whether the action succeeded
        error_message: Error details if success=False
    
    Returns:
        AuditLog: The created audit log entry
    """
    actor_id, actor_email, actor_name = get_user_identity_meta()
    if actor_user_id is not None:
        actor_id = actor_user_id
    if actor_user_email is not None:
        actor_email = actor_user_email
    if actor_user_name is not None:
        actor_name = actor_user_name
    log = AuditLog(
        user_id=actor_id if actor_id is not None else get_user_id(),
        user_email=actor_email,
        user_name=actor_name,
        action=action,
        target_type=target_type,
        target_id=target_id,
        target_name=target_name,
        description=description,
        old_value=json.dumps(old_value, default=str) if old_value is not None else None,
        new_value=json.dumps(new_value, default=str) if new_value is not None else None,
        ip_address=get_client_ip(),
        user_agent=request.headers.get('User-Agent', 'UNKNOWN') if has_request_context() else 'SYSTEM',
        timestamp=datetime.now(timezone.utc),
        success=success,
        error_message=error_message,
    )
    
    try:
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"Failed to create audit log: {str(e)}")
    
    return log


