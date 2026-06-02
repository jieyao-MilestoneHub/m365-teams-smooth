"""The mock Entra adapter invites a guest and schedules an auto-revoke (time-boxed access)."""

from __future__ import annotations

from app.adapters.integrations.mock_entra import MockEntraAdapter
from app.domain import CapabilityRef, ExecutionStep, RunMode, StepStatus


def _step(name: str, params: dict[str, object]) -> ExecutionStep:
    return ExecutionStep(
        step_id="s1", capability=CapabilityRef(system="entra", name=name), params=params
    )


def test_invite_guest_live() -> None:
    adapter = MockEntraAdapter()
    result = adapter.execute(
        _step("entra.invite_guest", {"email": "vendor@example.com", "display_name": "Vendor"}),
        RunMode.LIVE,
    )
    assert result.status is StepStatus.OK
    assert result.after is not None
    guest = result.after["guest"]
    assert isinstance(guest, dict) and guest["status"] == "invited"


def test_schedule_revoke_live() -> None:
    adapter = MockEntraAdapter()
    result = adapter.execute(
        _step(
            "entra.schedule_access_revoke",
            {"principal": "vendor@example.com", "revoke_on": "2026-06-30"},
        ),
        RunMode.LIVE,
    )
    assert result.status is StepStatus.OK
    assert result.after is not None
    task = result.after["revoke_task"]
    assert isinstance(task, dict) and task["revoke_on"] == "2026-06-30"


def test_dry_run_invites_nobody() -> None:
    adapter = MockEntraAdapter()
    result = adapter.execute(
        _step("entra.invite_guest", {"email": "v@example.com"}), RunMode.DRY_RUN
    )
    assert result.status is StepStatus.DRY_RUN
    again = adapter.execute(
        _step("entra.invite_guest", {"email": "v@example.com"}), RunMode.DRY_RUN
    )
    assert again.before == {"guests": 0}
