"""The MCP server: the court's primary surface. Tools/resources are façades over CourtService.

``build_mcp_server`` wires the service into a FastMCP instance (stateless HTTP, so it mounts on the
FastAPI app without a long-lived session). All business logic stays in the service.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from app.mcp.tools import register_tools
from app.services.court_service import CourtService

MCP_PATH = "/mcp"


def build_mcp_server(service: CourtService) -> FastMCP:
    """Build the MCP server with the court tools registered against ``service``."""
    mcp = FastMCP(
        "AI Change Court",
        stateless_http=True,
        streamable_http_path="/",
    )
    register_tools(mcp, service)
    return mcp
