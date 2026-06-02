"""Options builds a feasible plan, or a safe alternative that marks the change unsafe."""

from __future__ import annotations

from app.agent.nodes.options import OptionsNode, feasible_from_actions
from app.agent.state import CourtState, initial_state, serialize
from app.domain import (
    Change,
    ExecutionPlan,
    ImpactEvidence,
    PlanKind,
    RequestedAction,
    RunMode,
)


def _state(change: Change) -> CourtState:
    state = initial_state(
        thread_id="t1",
        change_id=change.change_id,
        raw_request=change.raw_request,
        source="test",
        run_mode=RunMode.DRY_RUN,
    )
    state["change"] = serialize(change)
    state["impact"] = serialize(ImpactEvidence())
    return state


def test_feasible_plan_maps_actions_one_to_one() -> None:
    change = Change(
        change_id="c1",
        raw_request="x",
        requested_actions=[
            RequestedAction(system="github", capability_name="github.update_milestone_due"),
        ],
    )
    plan = feasible_from_actions(change)
    assert plan.kind is PlanKind.FEASIBLE
    assert plan.steps[0].capability.name == "github.update_milestone_due"


def test_node_uses_generic_feasible_without_a_planner() -> None:
    change = Change(
        change_id="c1",
        raw_request="x",
        subject="launch",
        requested_actions=[RequestedAction(system="github", capability_name="github.create_issue")],
    )
    result = OptionsNode({})(_state(change))
    plan = ExecutionPlan.model_validate(result["options"])
    assert plan.kind is PlanKind.FEASIBLE
    assert result["selected_plan"] == "feasible"


def test_safe_alternative_marks_change_unsafe() -> None:
    def _alt_planner(change: Change, impact: ImpactEvidence) -> ExecutionPlan:
        return ExecutionPlan(
            kind=PlanKind.SAFE_ALTERNATIVE,
            rationale="private preview instead of GA",
            supersedes_request=True,
        )

    change = Change(change_id="c1", raw_request="promise GA", subject="sso-ga")
    result = OptionsNode({"sso-ga": _alt_planner})(_state(change))

    plan = ExecutionPlan.model_validate(result["options"])
    updated = Change.model_validate(result["change"])
    assert plan.kind is PlanKind.SAFE_ALTERNATIVE
    assert updated.unsafe is True
    assert updated.unsafe_reason == "private preview instead of GA"
