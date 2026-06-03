"""The MCP tools drive a full trial: submit → get_trial → cast_verdict, all via the server."""

from __future__ import annotations

from typing import Any, cast

import pytest

from app.config import Settings
from app.container import build_court_service
from app.mcp.server import build_mcp_server
from app.services.court_service import CourtService


@pytest.fixture
def mcp():  # type: ignore[no-untyped-def]
    service: CourtService = build_court_service(
        Settings(force_all_mock=True, db_url="sqlite:///:memory:", dry_run_default=True)
    )
    return build_mcp_server(service)


async def _call(mcp: Any, name: str, args: dict[str, Any]) -> dict[str, Any]:
    outcome = cast("tuple[Any, dict[str, Any]]", await mcp.call_tool(name, args))
    return outcome[1]


async def test_all_court_tools_registered(mcp: Any) -> None:
    names = {t.name for t in await mcp.list_tools()}
    assert {"submit_change", "get_status", "get_trial", "cast_verdict"} <= names


async def test_get_trial_unknown_surfaces_typed_error(mcp: Any) -> None:
    from mcp.server.fastmcp.exceptions import ToolError

    with pytest.raises(ToolError) as excinfo:
        await _call(mcp, "get_trial", {"thread_id": "does-not-exist"})
    # The shared not_found mapping reaches the tool surface.
    assert "not_found" in str(excinfo.value)


async def test_submit_then_cast_via_tools(mcp: Any) -> None:
    summary = await _call(
        mcp, "submit_change", {"raw_request": "promise Customer A SSO is GA by 2026-06-17"}
    )
    assert summary["status"] == "awaiting_verdict"
    assert summary["unsafe"] is True
    thread_id = summary["thread_id"]

    trial = await _call(mcp, "get_trial", {"thread_id": thread_id})
    assert trial["options"]["kind"] == "safe_alternative"

    result = await _call(
        mcp,
        "cast_verdict",
        {
            "thread_id": thread_id,
            "verdict_type": "accept_alternative",
            "selected_plan": "safe_alternative",
        },
    )
    assert result["status"] == "done"
    assert result["audit_id"]
