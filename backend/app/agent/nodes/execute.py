"""Execute node (Executor): run the chosen plan's steps through their adapters, honoring run_mode.

Execution is gated by the verdict — a rejection runs nothing. Each step goes registry → adapter →
``execute(step, run_mode)``; DRY_RUN predicts with no side effects. A failing step is contained by
the adapter as a FAILED result (with a rollback hint) and recorded, so the run never crashes.
"""

from __future__ import annotations

from app.agent.state import CourtState, serialize
from app.domain import (
    ChangeStatus,
    ExecutionPlan,
    RunMode,
    StepResult,
    StepStatus,
    Verdict,
    VerdictType,
)
from app.ports.registry import IntegrationRegistry

_APPROVING = {
    VerdictType.APPROVE,
    VerdictType.APPROVE_INTERNAL_ONLY,
    VerdictType.ACCEPT_ALTERNATIVE,
}


class ExecuteNode:
    """Runs the plan's write steps when the verdict approves; honors the run mode."""

    def __init__(self, registry: IntegrationRegistry) -> None:
        self._registry = registry

    def __call__(self, state: CourtState) -> CourtState:
        run_mode = RunMode(state["run_mode"])
        plan = ExecutionPlan.model_validate(state["options"])
        errors = list(state.get("errors", []))

        verdict_data = state.get("verdict")
        approved = True
        if verdict_data is not None:
            approved = Verdict.model_validate(verdict_data).type in _APPROVING

        if not approved:
            return {"results": [], "status": ChangeStatus.DONE.value, "errors": errors}

        results: list[StepResult] = []
        for step in plan.steps:
            adapter = self._registry.get(step.capability.system)
            if adapter is None:
                results.append(
                    StepResult(
                        step_id=step.step_id,
                        status=StepStatus.FAILED,
                        error=f"no adapter for system '{step.capability.system}'",
                    )
                )
                continue
            result = adapter.execute(step, run_mode)
            results.append(result)
            if result.status is StepStatus.FAILED and result.error:
                errors.append(f"step {result.step_id} failed: {result.error}")

        had_failure = any(r.status is StepStatus.FAILED for r in results)
        status = ChangeStatus.FAILED if had_failure else ChangeStatus.DONE
        update: CourtState = {
            "results": [serialize(r) for r in results],
            "status": status.value,
            "errors": errors,
        }
        return update
