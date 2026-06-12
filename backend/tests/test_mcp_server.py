"""The MCP server exposes the court as tools and composes with the REST app."""

from __future__ import annotations

from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

from app.asgi import create_full_app
from app.config import Settings
from app.container import build_court_service
from app.mcp.server import build_mcp_server
from app.services.court_service import CourtService
from tests.conftest import REQUESTER


@pytest.fixture
def service() -> CourtService:
    return build_court_service(
        Settings(force_all_mock=True, db_url="sqlite:///:memory:", dry_run_default=True)
    )


def test_get_status_tool_is_registered(service: CourtService) -> None:
    mcp = build_mcp_server(service)
    # FastMCP.list_tools is async; exercise it through the event loop.
    import anyio

    names = {t.name for t in anyio.run(mcp.list_tools)}
    assert "get_status" in names


async def test_get_status_tool_reflects_the_service(service: CourtService) -> None:
    summary = service.submit_change(
        "slip the launch from 2026-06-10 to 2026-06-17", requester=REQUESTER
    )
    mcp = build_mcp_server(service)
    # call_tool returns (content_blocks, structured_result); we assert on the structured dict.
    outcome = cast(
        "tuple[Any, dict[str, Any]]",
        await mcp.call_tool("get_status", {"thread_id": summary.thread_id}),
    )
    assert outcome[1]["status"] == summary.status


def test_full_app_serves_health_with_mcp_mounted(service: CourtService) -> None:
    # The composed app runs the MCP session-manager lifespan and still serves REST health.
    with TestClient(create_full_app(service)) as client:
        assert client.get("/api/health").status_code == 200


def test_mcp_accepts_bare_mount_path_without_redirect(service: CourtService) -> None:
    # MCP clients do not follow redirects: POST /mcp must reach the server directly (no 307),
    # whichever way the manifest spells the endpoint.
    with TestClient(create_full_app(service)) as client:
        for path in ("/mcp", "/mcp/"):
            response = client.post(path, follow_redirects=False)
            assert response.status_code != 307, path
