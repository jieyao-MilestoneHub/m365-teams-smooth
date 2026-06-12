"""Execute honors run_mode, the verdict gate, and contains a failing step without crashing."""

from __future__ import annotations

from app.agent.nodes.execute import ExecuteNode
from app.agent.state import CourtState, initial_state, serialize
from app.domain import (
    CapabilityRef,
    ChangeStatus,
    ExecutionPlan,
    ExecutionStep,
    PlanKind,
    RunMode,
    Verdict,
    VerdictType,
)
from app.domain.run_events import RunEventKind
from tests.conftest import InMemoryRunEventSink, build_mock_registry


def _plan() -> ExecutionPlan:
    return ExecutionPlan(
        kind=PlanKind.FEASIBLE,
        steps=[
            ExecutionStep(
                step_id="s1",
                capability=CapabilityRef(system="github", name="github.update_milestone_due"),
                params={"milestone": "Launch", "due_on": "2026-06-17"},
            ),
            ExecutionStep(
                step_id="s2",
                capability=CapabilityRef(system="planner", name="planner.shift_task_dates"),
                params={"delta_days": 7},
            ),
        ],
    )


def _state(run_mode: RunMode, verdict: Verdict | None) -> CourtState:
    state = initial_state(
        thread_id="t1", change_id="c1", raw_request="x", source="t", run_mode=run_mode
    )
    state["options"] = serialize(_plan())
    if verdict is not None:
        state["verdict"] = serialize(verdict)
    return state


def _approve() -> Verdict:
    return Verdict(verdict_id="v1", type=VerdictType.APPROVE, idempotency_key="k1")


def test_dry_run_predicts_all_steps() -> None:
    node = ExecuteNode(build_mock_registry())
    result = node(_state(RunMode.DRY_RUN, _approve()))
    statuses = [r["status"] for r in result["results"]]
    assert statuses == ["dry_run", "dry_run"]
    assert result["status"] == ChangeStatus.DONE.value


def test_live_approve_executes() -> None:
    node = ExecuteNode(build_mock_registry())
    result = node(_state(RunMode.LIVE, _approve()))
    assert [r["status"] for r in result["results"]] == ["ok", "ok"]


def test_reject_executes_nothing() -> None:
    reject = Verdict(verdict_id="v1", type=VerdictType.REJECT, idempotency_key="k1")
    node = ExecuteNode(build_mock_registry())
    result = node(_state(RunMode.LIVE, reject))
    assert result["results"] == []


def test_partial_failure_is_contained() -> None:
    node = ExecuteNode(build_mock_registry(planner_fail_on="planner.shift_task_dates"))
    result = node(_state(RunMode.LIVE, _approve()))  # must not raise
    statuses = [r["status"] for r in result["results"]]
    assert statuses == ["ok", "failed"]
    assert result["status"] == ChangeStatus.FAILED.value
    assert any("s2 failed" in e for e in result["errors"])


def test_steps_emit_started_and_finished_run_events() -> None:
    sink = InMemoryRunEventSink()
    node = ExecuteNode(build_mock_registry(), sink=sink)
    node(_state(RunMode.DRY_RUN, _approve()))

    assert [(e.kind, e.name) for e in sink.events] == [
        (RunEventKind.STEP_STARTED, "s1"),
        (RunEventKind.STEP_FINISHED, "s1"),
        (RunEventKind.STEP_STARTED, "s2"),
        (RunEventKind.STEP_FINISHED, "s2"),
    ]
    finished = sink.events[1]
    assert finished.status == "dry_run"
    assert finished.payload["system"] == "github"
    assert finished.payload["capability"] == "github.update_milestone_due"
    assert finished.payload["run_mode"] == "dry_run"


def test_failed_step_run_event_carries_error() -> None:
    sink = InMemoryRunEventSink()
    node = ExecuteNode(
        build_mock_registry(planner_fail_on="planner.shift_task_dates"), sink=sink
    )
    node(_state(RunMode.LIVE, _approve()))

    failed = [e for e in sink.events if e.kind is RunEventKind.STEP_FINISHED][-1]
    assert failed.name == "s2"
    assert failed.status == "failed"
    assert failed.payload["error"]

def test_analyze_skips_execution_even_with_an_approving_verdict() -> None:
    # The analyze check sits before the verdict gate: not even an injected APPROVE runs a step.
    node = ExecuteNode(build_mock_registry())
    result = node(_state(RunMode.ANALYZE, _approve()))
    assert result["results"] == []
    assert result["status"] == ChangeStatus.ANALYZED.value
