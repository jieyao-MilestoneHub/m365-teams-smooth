"""Correlation binding at the MCP entry: the ``correlate`` helper used in tool/resource calls."""

from __future__ import annotations

import json
import logging
from typing import Any, cast

import pytest

from app.config import Settings
from app.container import build_court_service
from app.mcp import correlate
from app.mcp.server import build_mcp_server
from app.observability.context import current_context
from app.observability.logging import JsonFormatter
from app.services.court_service import CourtService


@pytest.fixture
def service() -> CourtService:
    return build_court_service(
        Settings(force_all_mock=True, db_url="sqlite:///:memory:", dry_run_default=True)
    )


async def _call(mcp: Any, name: str, args: dict[str, Any]) -> dict[str, Any]:
    outcome = cast("tuple[Any, dict[str, Any]]", await mcp.call_tool(name, args))
    return outcome[1]


class _CaptureHandler(logging.Handler):
    """Format each record on emit (inside the bound scope) and keep the JSON string."""

    def __init__(self) -> None:
        super().__init__()
        self.setFormatter(JsonFormatter())
        self.formatted: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.formatted.append(self.format(record))


def test_correlate_binds_request_and_thread_id() -> None:
    seen: dict[str, str] = {}

    @correlate
    def probe(thread_id: str) -> None:
        seen.update(current_context())

    probe(thread_id="t-1")

    assert seen["thread_id"] == "t-1"
    assert seen["request_id"]  # a generated uuid hex
    assert current_context() == {}  # reset after the call


def test_correlate_binds_only_request_id_without_thread() -> None:
    seen: dict[str, str] = {}

    @correlate
    def probe() -> None:
        seen.update(current_context())

    probe()

    assert set(seen) == {"request_id"}


def test_correlate_record_carries_correlation() -> None:
    handler = _CaptureHandler()

    @correlate
    def probe(thread_id: str) -> None:
        logging.getLogger("app.mcp.probe").info("inside")

    logger = logging.getLogger("app.mcp.probe")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    try:
        probe(thread_id="t-7")
    finally:
        logger.removeHandler(handler)

    payload = json.loads(handler.formatted[0])
    assert payload["thread_id"] == "t-7"
    assert payload["request_id"]


async def test_tool_call_binds_correlation(
    service: CourtService, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, str] = {}
    original = service.get_status

    def spy(thread_id: str) -> str | None:
        seen.update(current_context())
        return original(thread_id)

    monkeypatch.setattr(service, "get_status", spy)
    mcp = build_mcp_server(service)

    await _call(mcp, "get_status", {"thread_id": "t-xyz"})

    assert seen["thread_id"] == "t-xyz"
    assert seen["request_id"]


async def test_resource_call_binds_request_id(
    service: CourtService, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, str] = {}
    original = service.capabilities

    def spy() -> Any:
        seen.update(current_context())
        return original()

    monkeypatch.setattr(service, "capabilities", spy)
    mcp = build_mcp_server(service)

    await mcp.read_resource("court://capabilities")

    assert seen["request_id"]
