"""The MCP server: the court's primary surface. Tools/resources are façades over CourtService.

``build_mcp_server`` wires the service into a FastMCP instance (stateless HTTP, so it mounts on the
FastAPI app without a long-lived session). All business logic stays in the service.
"""

from __future__ import annotations

from typing import Any

from mcp.server.auth.provider import TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from app.mcp.resources import register_resources
from app.mcp.tools import register_tools
from app.services.court_service import CourtService

MCP_PATH = "/mcp"


def build_mcp_server(
    service: CourtService,
    *,
    token_verifier: TokenVerifier | None = None,
    auth_settings: AuthSettings | None = None,
    transport_security: TransportSecuritySettings | None = None,
) -> FastMCP:
    """Build the MCP server with the court tools and resources registered against ``service``.

    Passing a ``token_verifier`` + ``auth_settings`` turns the server into an OAuth2-protected
    resource server; omitting them leaves it open for local development. ``transport_security``
    allow-lists the public Host header when serving behind an ingress.
    """
    kwargs: dict[str, Any] = {"stateless_http": True, "streamable_http_path": "/"}
    if token_verifier is not None and auth_settings is not None:
        kwargs["token_verifier"] = token_verifier
        kwargs["auth"] = auth_settings
    if transport_security is not None:
        kwargs["transport_security"] = transport_security
    mcp = FastMCP("AI Change Court", **kwargs)
    register_tools(mcp, service)
    register_resources(mcp, service)
    return mcp
