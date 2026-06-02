"""The mock SharePoint adapter flags customer-data folders and grants scoped, expiring access."""

from __future__ import annotations

from app.adapters.integrations.mock_sharepoint import MockSharePointAdapter
from app.domain import CapabilityRef, ExecutionStep, RunMode, StepStatus
from app.ports.integration import ReadQuery


def test_launch_assets_has_no_customer_data() -> None:
    adapter = MockSharePointAdapter()
    data = adapter.read(
        ReadQuery(capability="sharepoint.read_folder", params={"path": "/ProjectX/LaunchAssets"})
    ).data
    assert data["contains_customer_data"] is False


def test_project_root_holds_customer_data() -> None:
    adapter = MockSharePointAdapter()
    data = adapter.read(
        ReadQuery(capability="sharepoint.read_folder", params={"path": "/ProjectX"})
    ).data
    assert data["contains_customer_data"] is True


def test_grant_records_scoped_permission_with_expiry() -> None:
    adapter = MockSharePointAdapter()
    step = ExecutionStep(
        step_id="s1",
        capability=CapabilityRef(system="sharepoint", name="sharepoint.grant_folder_permission"),
        params={
            "path": "/ProjectX/LaunchAssets",
            "principal": "vendor@example.com",
            "role": "read",
            "expiry": "2026-06-30",
        },
    )
    result = adapter.execute(step, RunMode.LIVE)
    assert result.status is StepStatus.OK
    assert result.after is not None
    grant = result.after["grant"]
    assert isinstance(grant, dict)
    assert grant["role"] == "read" and grant["expiry"] == "2026-06-30"
