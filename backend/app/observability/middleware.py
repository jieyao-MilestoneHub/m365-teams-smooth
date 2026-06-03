"""HTTP correlation middleware: bind a ``request_id`` for the duration of each request.

Reads an inbound ``X-Request-ID`` (or generates a uuid4 hex), binds it into the correlation context
so every log line emitted while handling the request carries it, and echoes it on the response. The
MCP server is a separate ASGI sub-app not covered by this middleware — it binds inside its
tool/resource closures (#185).
"""

from __future__ import annotations

from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.observability.context import bind, reset

REQUEST_ID_HEADER = "X-Request-ID"


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Bind an inbound-or-generated request ID for the request scope and echo it back."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid4().hex
        tokens = bind(request_id=request_id)
        try:
            response = await call_next(request)
        finally:
            reset(tokens)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
