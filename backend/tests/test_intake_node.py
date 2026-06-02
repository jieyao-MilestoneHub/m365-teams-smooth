"""Intake delegates parsing to a RequestParser; the guard rejects unsupported actions."""

from __future__ import annotations

from app.adapters.integrations.registry import ConfigIntegrationRegistry
from app.adapters.parsers.deterministic import DeterministicRequestParser
from app.agent.nodes.intake import IntakeNode
from app.agent.state import CourtState, initial_state
from app.domain import Change, ChangeStatus, RunMode


def _state(raw: str) -> CourtState:
    return initial_state(
        thread_id="t1", change_id="c1", raw_request=raw, source="test", run_mode=RunMode.DRY_RUN
    )


def _node(registry: ConfigIntegrationRegistry) -> IntakeNode:
    return IntakeNode(DeterministicRequestParser(), registry)


def test_guard_rejects_delete_repo(mock_registry: ConfigIntegrationRegistry) -> None:
    raw = "slip the launch from 2026-06-10 to 2026-06-17, also delete the old launch repo"
    result = _node(mock_registry)(_state(raw))

    change = Change.model_validate(result["change"])
    names = [a.capability_name for a in change.requested_actions]
    assert "github.update_milestone_due" in names  # supported action survives
    assert "github.delete_repo" not in names  # unsupported action is dropped
    assert any("github.delete_repo" in e for e in result["errors"])  # recorded as rejected
    assert result["status"] == ChangeStatus.EVALUATING.value  # the rest still proceeds


def test_guard_blocks_when_all_unsupported() -> None:
    # An empty registry supports nothing, so the only action is rejected and the change blocks.
    result = _node(ConfigIntegrationRegistry([]))(_state("give the vendor access to Project X"))
    assert result["status"] == ChangeStatus.BLOCKED.value
