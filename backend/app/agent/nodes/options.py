"""Options node (Defender): a feasible plan, or a safe alternative for an unsafe request.

The node dispatches to the planner registered for the change's subject and falls back to a generic
plan mapping the requested actions one-to-one. When the chosen plan is a safe alternative, the
change is marked unsafe so policy and the verdict surface it.
"""

from __future__ import annotations

import logging
from typing import Protocol

from app.agent.deliberate import Deliberator, OfflineDeliberator, record
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
from app.observability import metrics

logger = logging.getLogger(__name__)


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

    def __init__(
        self,
        planners: dict[str, Planner],
        deliberator: Deliberator | None = None,
        *,
        default_planner: Planner | None = None,
    ) -> None:
        self._planners = planners
        self._deliberator = deliberator or OfflineDeliberator()
        self._default_planner = default_planner

    def __call__(self, state: CourtState) -> CourtState:
        change = Change.model_validate(state["change"])
        impact = ImpactEvidence.model_validate(state.get("impact", {"items": [], "tags": []}))

        registered = self._planners.get(change.subject or "")
        planner = registered or self._default_planner
        if registered is None:
            # No specialized planner: the default (or the bare 1:1 plan) is correct but
            # unconsidered — keep the gap observable either way.
            logger.info("planner.not_registered", extra={"subject": change.subject})
            metrics.increment("planners.fallback")
        plan = planner(change, impact) if planner is not None else feasible_from_actions(change)

        if plan.kind is PlanKind.SAFE_ALTERNATIVE:
            change.unsafe = True
            change.unsafe_reason = plan.rationale

        # The Defender (when LLM-backed) reasons in the plan rationale; reuse it as the options
        # reasoning. Offline, the deliberator records the factual plan summary instead.
        stance = (
            "refused as posed, proposing a safe alternative"
            if plan.kind is PlanKind.SAFE_ALTERNATIVE
            else "feasible as requested"
        )
        context = (
            f"Plan is {stance}: {len(plan.steps)} step(s) across "
            f"{', '.join(sorted({s.capability.system for s in plan.steps})) or 'no systems'}."
        )
        entry = self._deliberator.deliberate(
            node="options", role="defender", context=context, reasoning=plan.rationale
        )

        update: CourtState = {
            "options": serialize(plan),
            "change": serialize(change),
            "selected_plan": plan.kind.value,
            "status": ChangeStatus.EVALUATING.value,
            "deliberations": record(state, entry),
        }
        return update
