"""Deployment ASGI app: the REST health surface plus the mounted MCP server.

Composition happens here, at the edge — ``create_app`` stays health-only and the MCP server stays a
façade over the service. Serve with ``uvicorn app.asgi:app``. The MCP endpoint is at ``/mcp``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.types import ASGIApp, Receive, Scope, Send

from app.api.deps import get_court_service
from app.config import Settings
from app.main import create_app
from app.mcp.security import build_auth_settings, build_token_verifier, build_transport_security
from app.mcp.server import MCP_PATH, build_mcp_server
from app.observability import configure_logging, configure_metrics
from app.services.court_service import CourtService


class MountPathNormalizer:
    """Rewrite the bare mount path to the mounted root instead of redirecting.

    Starlette answers ``POST /mcp`` with a 307 to ``/mcp/``; MCP clients (e.g. the Copilot
    plugin runtime) do not follow redirects, so the tool call silently dies. Normalizing the
    path here makes both spellings reach the mounted server directly.
    """

    def __init__(self, app: ASGIApp, mount_path: str) -> None:
        self._app = app
        self._mount_path = mount_path.rstrip("/")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope.get("path") == self._mount_path:
            scope["path"] = self._mount_path + "/"
            scope["raw_path"] = scope["path"].encode("ascii")
        await self._app(scope, receive, send)


def create_full_app(service: CourtService | None = None) -> FastAPI:
    """Build the REST app and mount the OAuth2-protected MCP server, run via the lifespan."""
    settings = Settings()
    configure_logging(settings)
    configure_metrics(settings)
    mcp = build_mcp_server(
        service or get_court_service(),
        token_verifier=build_token_verifier(settings),
        auth_settings=build_auth_settings(settings),
        transport_security=build_transport_security(settings),
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        async with mcp.session_manager.run():
            yield

    app = create_app(lifespan=lifespan)
    app.mount(MCP_PATH, mcp.streamable_http_app())
    app.add_middleware(MountPathNormalizer, mount_path=MCP_PATH)
    return app


app = create_full_app()
