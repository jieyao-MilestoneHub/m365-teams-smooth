"""Typed error mapping shared by the REST and MCP surfaces.

The same domain-error hierarchy must produce the same response on both edges, so the classification
lives here once. REST renders it as an HTTP status + ``{error, detail, request_id}`` body via the
registered exception handlers; the MCP tools render it as a raised structured error carrying the
same payload (see ``app/mcp/tools.py``). The ``request_id`` is read from the correlation context
bound by the HTTP middleware (or the MCP entry point), so an error line and its response agree.
"""

from __future__ import annotations

import logging
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from mcp.types import INTERNAL_ERROR, INVALID_PARAMS

from app.domain.errors import (
    CapabilityNotFoundError,
    ChangeCourtError,
    IntegrationError,
    NotFoundError,
    UnsafeChangeError,
    VerdictConflictError,
)
from app.observability.context import current_context

logger = logging.getLogger(__name__)

# Most-specific first; the base ``ChangeCourtError`` is the catch-all for our own typed errors.
_MAPPING: list[tuple[type[ChangeCourtError], int, str]] = [
    (NotFoundError, 404, "not_found"),
    (CapabilityNotFoundError, 422, "capability_not_found"),
    (UnsafeChangeError, 409, "unsafe_change"),
    (VerdictConflictError, 409, "verdict_conflict"),
    (IntegrationError, 502, "integration_error"),
    (ChangeCourtError, 500, "internal_error"),
]

# JSON-RPC codes for the MCP surface. App-defined errors use the server-reserved -320xx range.
_MCP_CODES: dict[str, int] = {
    "not_found": -32004,
    "capability_not_found": INVALID_PARAMS,
    "unsafe_change": -32009,
    "verdict_conflict": -32009,
    "integration_error": -32002,
    "internal_error": INTERNAL_ERROR,
}


def classify(exc: Exception) -> tuple[int, str]:
    """Map an exception to its ``(http_status, error_code)``. Unknown errors are internal 500s."""
    for exc_type, status, code in _MAPPING:
        if isinstance(exc, exc_type):
            return status, code
    return 500, "internal_error"


def mcp_code(code: str) -> int:
    """The JSON-RPC error code for a logical ``error_code`` slug."""
    return _MCP_CODES.get(code, INTERNAL_ERROR)


def error_body(code: str, detail: str, request_id: str) -> dict[str, str]:
    """The shared error payload returned by both surfaces."""
    return {"error": code, "detail": detail, "request_id": request_id}


def current_request_id() -> str:
    """The request ID bound for this scope, or a fresh one when no context is active."""
    return current_context().get("request_id") or uuid4().hex


def register_exception_handlers(app: FastAPI) -> None:
    """Register the typed domain-error and catch-all handlers on a FastAPI app."""

    @app.exception_handler(ChangeCourtError)
    async def _handle_domain(_request: Request, exc: Exception) -> JSONResponse:
        status, code = classify(exc)
        request_id = current_request_id()
        # The correlation context already carries request_id onto the log line.
        logger.warning("domain error (%s): %s", code, exc)
        return JSONResponse(
            status_code=status, content=error_body(code, str(exc), request_id)
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected(_request: Request, exc: Exception) -> JSONResponse:
        request_id = current_request_id()
        # Log the full exception; never leak its detail to the client.
        logger.exception("unhandled error: %s", exc)
        return JSONResponse(
            status_code=500, content=error_body("internal_error", "internal error", request_id)
        )
