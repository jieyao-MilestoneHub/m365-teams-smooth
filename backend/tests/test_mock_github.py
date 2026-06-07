"""The mock GitHub adapter reads milestone/blockers and updates the milestone due date."""

from __future__ import annotations

from app.adapters.integrations.mock_github import MockGitHubAdapter
from app.domain import CapabilityRef, ExecutionStep, RunMode, StepStatus
from app.ports.integration import ReadQuery


def test_milestone_and_blockers_are_seeded() -> None:
    adapter = MockGitHubAdapter()
    milestone = adapter.read(
        ReadQuery(capability="github.read_milestone", params={"milestone": "Launch Rehearsal"})
    ).data
    assert milestone["due_on"] == "2026-06-10"
    blockers = adapter.read(ReadQuery(capability="github.read_blocking_issues")).data["issues"]
    assert isinstance(blockers, list) and len(blockers) == 2


def test_closed_issues_filter_by_since() -> None:
    adapter = MockGitHubAdapter()
    all_closed = adapter.read(ReadQuery(capability="github.read_closed_issues")).data["issues"]
    assert isinstance(all_closed, list) and len(all_closed) == 4
    recent = adapter.read(
        ReadQuery(capability="github.read_closed_issues", params={"since": "2026-06-05"})
    ).data["issues"]
    assert isinstance(recent, list)
    assert [i["number"] for i in recent] == [38, 40]


def test_update_milestone_due_live_with_before_snapshot() -> None:
    adapter = MockGitHubAdapter()
    step = ExecutionStep(
        step_id="s1",
        capability=CapabilityRef(system="github", name="github.update_milestone_due"),
        params={"milestone": "Launch Rehearsal", "due_on": "2026-06-17"},
    )
    result = adapter.execute(step, RunMode.LIVE)
    assert result.status is StepStatus.OK
    assert result.before == {"title": "Launch Rehearsal", "due_on": "2026-06-10"}
    after = adapter.read(
        ReadQuery(capability="github.read_milestone", params={"milestone": "Launch Rehearsal"})
    ).data
    assert after["due_on"] == "2026-06-17"


def test_dry_run_does_not_move_milestone() -> None:
    adapter = MockGitHubAdapter()
    step = ExecutionStep(
        step_id="s1",
        capability=CapabilityRef(system="github", name="github.update_milestone_due"),
        params={"milestone": "Launch Rehearsal", "due_on": "2026-06-17"},
    )
    assert adapter.execute(step, RunMode.DRY_RUN).status is StepStatus.DRY_RUN
    after = adapter.read(
        ReadQuery(capability="github.read_milestone", params={"milestone": "Launch Rehearsal"})
    ).data
    assert after["due_on"] == "2026-06-10"  # unchanged
