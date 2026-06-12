"""The MCP resources expose the trial, audit record, and capability catalog over court:// URIs."""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.config import Settings
from app.container import build_court_service
from app.mcp.server import build_mcp_server
from app.services.court_service import CourtService
from tests.conftest import ALL_ROLE_DIRECTORY, APPROVER, REQUESTER


@pytest.fixture
def service() -> CourtService:
    return build_court_service(
        Settings(
            force_all_mock=True,
            db_url="sqlite:///:memory:",
            dry_run_default=True,
            approver_directory=ALL_ROLE_DIRECTORY,
        )
    )


async def _read(mcp: Any, uri: str) -> Any:
    contents = await mcp.read_resource(uri)
    return json.loads(contents[0].content)


async def test_capabilities_resource_lists_the_catalog(service: CourtService) -> None:
    mcp = build_mcp_server(service)
    catalog = await _read(mcp, "court://capabilities")
    names = {c["name"] for c in catalog}
    assert "github.update_milestone_due" in names
    assert "sharepoint.grant_folder_permission" in names


async def test_trial_and_audit_resources(service: CourtService) -> None:
    mcp = build_mcp_server(service)
    summary = service.submit_change(
        "slip the launch from 2026-06-10 to 2026-06-17", requester=REQUESTER
    )

    trial = await _read(mcp, f"court://trial/{summary.thread_id}")
    assert trial["change"]["change_id"] == summary.change_id

    from app.domain import VerdictType

    cast = service.cast_verdict(summary.thread_id, VerdictType.APPROVE, principal=APPROVER)
    assert cast.audit_id is not None
    audit = await _read(mcp, f"court://audit/{cast.audit_id}")
    assert audit["audit_id"] == cast.audit_id
    assert audit["run_mode"] == "dry_run"
    # The published payload keeps the derived views even though they are no longer stored fields.
    assert "before_after" in audit and "rollback_hints" in audit
