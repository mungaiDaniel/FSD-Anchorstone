"""
Change-request handlers: one per request_type.

A handler turns a payload into a change. It is plain Python registered here:

    @register
    class GrantRole(Handler):
        request_type = "rbac.grant_role"
        submit_permission = "role.manage"
        def validate(self, payload) -> dict: ...        # normalised payload; raise ValidationError
        def apply(self, request, actor) -> dict: ...    # do it; return a result for the record and audit

validate() runs at submit, at resubmit and again at final approval (under the
same locks the direct action would take). base_version() returns a fingerprint
of the target's current state; approval refuses if it changed since submit.
"""
from decimal import Decimal

from app.Admin.model import User

HANDLERS: dict[str, "Handler"] = {}


class Handler:
    request_type: str = ""
    entity_type: str | None = None
    submit_permission: str = ""

    def validate(self, payload: dict) -> dict:
        return payload

    def entity_id(self, payload: dict) -> str | None:
        return None

    def base_version(self, payload: dict) -> str | None:
        return None

    def amount(self, payload: dict) -> Decimal | None:
        return None

    def branch_id(self, payload: dict) -> int | None:
        return None

    def describe(self, payload: dict) -> str:
        return self.request_type

    def apply(self, request, actor: User) -> dict:
        raise NotImplementedError

    def old_value(self, payload: dict):
        return None


def register(cls):
    handler = cls()
    if not handler.request_type or not handler.submit_permission:
        raise TypeError(f"{cls.__name__} needs request_type and submit_permission")
    if handler.request_type in HANDLERS:
        raise TypeError(f"Duplicate change-request handler {handler.request_type}")
    HANDLERS[handler.request_type] = handler
    return cls


def load_handlers() -> None:
    """Import every module that registers handlers (called once from create_app)."""
    import app.Access.handlers  # noqa: F401
