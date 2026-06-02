"""Options node (Defender): a feasible plan, or a safe alternative for an unsafe request.

The node dispatches to the planner registered for the change's subject (the trial planners, with
the safe-alternative builders, land in #85) and falls back to a generic plan mapping the requested
actions one-to-one. When the chosen plan is a safe alternative, the change is marked unsafe so
policy and the verdict surface it.
"""

from __future__ import annotations

from typing import Protocol

from app.agent.state import CourtState, serialize
from app.domain import (
    CapabilityRef,
    Change,
    ChangeStatus,
    ExecutionPlan,
    ExecutionStep,
    ImpactEvidence,
    PlanKind,
)


class Planner(Protocol):
    """Builds the execution plan for one change subject (feasible or a safe alternative)."""

    def __call__(self, change: Change, impact: ImpactEvidence) -> ExecutionPlan: ...


def feasible_from_actions(change: Change) -> ExecutionPlan:
    """Map each validated requested action to one execution step (the generic feasible plan)."""
    steps = [
        ExecutionStep(
            step_id=f"s{i + 1}",
            capability=CapabilityRef(system=action.system, name=action.capability_name),
            params=dict(action.params),
        )
        for i, action in enumerate(change.requested_actions)
    ]
    return ExecutionPlan(
        kind=PlanKind.FEASIBLE,
        steps=steps,
        rationale="Execute the requested actions.",
    )


class OptionsNode:
    """Selects the plan for the change, marking it unsafe when a safe alternative is produced."""

    def __init__(self, planners: dict[str, Planner]) -> None:
        self._planners = planners

    def __call__(self, state: CourtState) -> CourtState:
        change = Change.model_validate(state["change"])
        impact = ImpactEvidence.model_validate(state.get("impact", {"items": [], "tags": []}))

        planner = self._planners.get(change.subject or "")
        plan = planner(change, impact) if planner is not None else feasible_from_actions(change)

        if plan.kind is PlanKind.SAFE_ALTERNATIVE:
            change.unsafe = True
            change.unsafe_reason = plan.rationale

        update: CourtState = {
            "options": serialize(plan),
            "change": serialize(change),
            "selected_plan": plan.kind.value,
            "status": ChangeStatus.EVALUATING.value,
        }
        return update
