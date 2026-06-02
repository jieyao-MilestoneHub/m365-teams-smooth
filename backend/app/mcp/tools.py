"""MCP tools — thin façades over CourtService. No business logic lives here.

Tools are registered as closures capturing the service, so the server is built by dependency
injection (and unit-tested by calling the service directly or via ``FastMCP.call_tool``).
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from app.services.court_service import CourtService


def register_tools(mcp: FastMCP, service: CourtService) -> None:
    """Register the court tools on the MCP server."""

    @mcp.tool()
    def get_status(thread_id: str) -> dict[str, object]:
        """Return the current lifecycle status of a trial."""
        return {"thread_id": thread_id, "status": service.get_status(thread_id)}
