"""Deployment ASGI app: the REST health surface plus the mounted MCP server.

Composition happens here, at the edge — ``create_app`` stays health-only and the MCP server stays a
façade over the service. Serve with ``uvicorn app.asgi:app``. The MCP endpoint is at ``/mcp``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.deps import get_court_service
from app.main import create_app
from app.mcp.server import MCP_PATH, build_mcp_server
from app.services.court_service import CourtService


def create_full_app(service: CourtService | None = None) -> FastAPI:
    """Build the REST app and mount the MCP server, running its session manager via the lifespan."""
    mcp = build_mcp_server(service or get_court_service())

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        async with mcp.session_manager.run():
            yield

    app = create_app(lifespan=lifespan)
    app.mount(MCP_PATH, mcp.streamable_http_app())
    return app


app = create_full_app()
