"""
Uniform JSON responses and error handling for every endpoint.

Success:  {"status": 200, "message": "...", "data": ...}
Error:    {"status": 4xx, "message": "..."}

Services raise ApiError subclasses for expected failures (bad input, business
rule violations); the handler registered in main.py turns them into JSON so
routes don't need their own try/except blocks.
"""
import logging

from flask import jsonify, make_response
from werkzeug.exceptions import HTTPException

logger = logging.getLogger(__name__)


class ApiError(Exception):
    status_code = 400

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        if status_code is not None:
            self.status_code = status_code


class ValidationError(ApiError):
    status_code = 400


class Forbidden(ApiError):
    status_code = 403


class NotFound(ApiError):
    status_code = 404


class Conflict(ApiError):
    status_code = 409


def ok(data=None, message: str = "OK", status: int = 200):
    body = {"status": status, "message": message}
    if data is not None:
        body["data"] = data
    return make_response(jsonify(body), status)


def error(message: str, status: int, code: str | None = None):
    body = {"status": status, "message": message}
    if code:
        body["code"] = code  # machine-readable, for the frontend to act on
    return make_response(jsonify(body), status)


def page_args(args, default_per_page: int = 50, max_per_page: int = 200) -> tuple[int, int]:
    try:
        page = max(int(args.get("page") or 1), 1)
        per_page = min(max(int(args.get("per_page") or default_per_page), 1), max_per_page)
    except ValueError:
        raise ValidationError("page and per_page must be whole numbers.")
    return page, per_page


def paginate(query, page: int, per_page: int, serialize) -> dict:
    total = query.count()
    items = query.limit(per_page).offset((page - 1) * per_page).all()
    return {"items": [serialize(i) for i in items], "total": total, "page": page, "per_page": per_page}


def register_error_handlers(app, db):
    @app.errorhandler(ApiError)
    def _api_error(e: ApiError):
        db.session.rollback()
        return error(e.message, e.status_code)

    @app.errorhandler(HTTPException)
    def _http_error(e: HTTPException):
        return error(e.description or e.name, e.code or 500)

    @app.errorhandler(Exception)
    def _unhandled(e: Exception):
        db.session.rollback()
        logger.error("Unhandled error", exc_info=True)
        return error("An unexpected error occurred.", 500)
