"""One JSON error shape for the whole API.

Every failure returns {"error": {"code", "message", "field_errors"}} so the
frontend can branch on a stable code instead of parsing prose.
"""

import logging

from django.db import DatabaseError
from rest_framework import status
from rest_framework.response import Response

logger = logging.getLogger(__name__)


class ApiError(Exception):
    """Raised by application code to produce a specific, user-safe failure."""

    def __init__(self, code: str, message: str, http_status: int, field_errors: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.field_errors = field_errors or {}


def error_response(code: str, message: str, http_status: int, field_errors: dict | None = None) -> Response:
    body = {"error": {"code": code, "message": message}}
    if field_errors:
        body["error"]["field_errors"] = field_errors
    return Response(body, status=http_status)


# DRF's default codes are not stable enough to branch on, so they are mapped.
_STATUS_CODES = {
    400: "invalid_request",
    401: "authentication_required",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    413: "file_too_large",
    415: "unsupported_media_type",
    429: "rate_limited",
}


def api_exception_handler(exc, context):
    # Imported here, not at module scope: DRF loads this module while building
    # its settings, so a top-level import of rest_framework.views is circular.
    from rest_framework.views import exception_handler as drf_exception_handler

    if isinstance(exc, ApiError):
        return error_response(exc.code, exc.message, exc.http_status, exc.field_errors)

    response = drf_exception_handler(exc, context)

    if response is not None:
        detail = response.data
        field_errors: dict = {}
        message = "The request could not be completed."

        if isinstance(detail, dict):
            if "detail" in detail:
                message = str(detail["detail"])
            else:
                field_errors = {k: [str(m) for m in (v if isinstance(v, list) else [v])] for k, v in detail.items()}
                message = "Some fields need attention."
        elif isinstance(detail, list):
            message = "; ".join(str(item) for item in detail)

        code = _STATUS_CODES.get(response.status_code, "request_failed")
        return error_response(code, message, response.status_code, field_errors)

    # Unhandled: log the real cause server-side, tell the client nothing useful
    # to an attacker.
    if isinstance(exc, DatabaseError):
        logger.exception("Database error while handling %s", context.get("request"))
        return error_response(
            "database_unavailable",
            "The service could not reach its database. Please try again.",
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    logger.exception("Unhandled error while handling %s", context.get("request"))
    return None
