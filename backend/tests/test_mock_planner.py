"""The mock Planner adapter shifts dates and, when injected, fails cleanly with a rollback hint."""

from __future__ import annotations

from app.adapters.integrations.mock_planner import MockPlannerAdapter
from app.domain import CapabilityRef, ExecutionStep, RunMode, StepStatus
from app.ports.integration import ReadQuery


def _shift_step() -> ExecutionStep:
    return ExecutionStep(
        step_id="s1",
        capability=CapabilityRef(system="planner", name="planner.shift_task_dates"),
        params={"delta_days": 7},
    )


def _tasks(adapter: MockPlannerAdapter) -> list[dict[str, object]]:
    tasks = adapter.read(ReadQuery(capability="planner.read_tasks")).data["tasks"]
    assert isinstance(tasks, list)
    return tasks


def test_live_shift_moves_due_dates() -> None:
    adapter = MockPlannerAdapter()
    result = adapter.execute(_shift_step(), RunMode.LIVE)
    assert result.status is StepStatus.OK
    assert _tasks(adapter)[0]["due"] == "2026-06-17"  # 2026-06-10 + 7


def test_injected_failure_is_contained_with_rollback() -> None:
    adapter = MockPlannerAdapter(fail_on="planner.shift_task_dates")
    result = adapter.execute(_shift_step(), RunMode.LIVE)  # must not raise
    assert result.status is StepStatus.FAILED
    assert result.error is not None
    assert result.rollback is not None
    assert result.rollback.params == {"delta_days": -7}


def test_dry_run_does_not_shift() -> None:
    adapter = MockPlannerAdapter()
    adapter.execute(_shift_step(), RunMode.DRY_RUN)
    assert _tasks(adapter)[0]["due"] == "2026-06-10"  # unchanged
