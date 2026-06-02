"""Intake parses the trials deterministically; the guard rejects unsupported actions."""

from __future__ import annotations

from app.adapters.integrations.registry import ConfigIntegrationRegistry
from app.agent.nodes.intake import IntakeNode, parse_request
from app.agent.state import CourtState, initial_state
from app.domain import Change, ChangeStatus, RunMode


def _state(raw: str) -> CourtState:
    return initial_state(
        thread_id="t1", change_id="c1", raw_request=raw, source="test", run_mode=RunMode.DRY_RUN
    )


def test_parse_launch_slip_extracts_target_date_and_action() -> None:
    change = parse_request("slip the launch from 2026-06-10 to 2026-06-17", change_id="c1")
    assert change.subject == "launch"
    assert change.due_by == "2026-06-17"
    assert change.requested_actions[0].capability_name == "github.update_milestone_due"


def test_parse_vendor_access_is_broad_and_undated() -> None:
    change = parse_request(
        "give the vendor access to Project X until the campaign is done", change_id="c1"
    )
    action = change.requested_actions[0]
    assert action.capability_name == "sharepoint.grant_folder_permission"
    assert action.params["path"] == "/ProjectX"
    assert "expiry" not in action.params  # options must add the expiry


def test_guard_rejects_delete_repo(mock_registry: ConfigIntegrationRegistry) -> None:
    node = IntakeNode(mock_registry)
    raw = "slip the launch from 2026-06-10 to 2026-06-17, also delete the old launch repo"
    result = node(_state(raw))

    change = Change.model_validate(result["change"])
    names = [a.capability_name for a in change.requested_actions]
    assert "github.update_milestone_due" in names  # supported action survives
    assert "github.delete_repo" not in names  # unsupported action is dropped
    assert any("github.delete_repo" in e for e in result["errors"])  # recorded as rejected
    assert result["status"] == ChangeStatus.EVALUATING.value  # the rest still proceeds


def test_guard_blocks_when_all_unsupported() -> None:
    # An empty registry supports nothing, so the only action is rejected and the change blocks.
    node = IntakeNode(ConfigIntegrationRegistry([]))
    result = node(_state("give the vendor access to Project X"))
    assert result["status"] == ChangeStatus.BLOCKED.value
