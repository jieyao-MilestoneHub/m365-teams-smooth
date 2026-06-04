"""Execute node (Executor): run the chosen plan's steps through their adapters, honoring run_mode.

Execution is gated by the verdict — a rejection runs nothing. Each step goes registry → adapter →
``execute(step, run_mode)``; DRY_RUN predicts with no side effects. A failing step is contained by
the adapter as a FAILED result (with a rollback hint) and recorded, so the run never crashes.
"""

from __future__ import annotations

import logging

from app.agent.state import CourtState, bound_errors, serialize
from app.domain import (
    ChangeStatus,
    ExecutionPlan,
    RunMode,
    StepResult,
    StepStatus,
    Verdict,
    VerdictType,
)
from app.observability import metrics
from app.ports.registry import IntegrationRegistry

logger = logging.getLogger(__name__)

_APPROVING = {
    VerdictType.APPROVE,
    VerdictType.APPROVE_INTERNAL_ONLY,
    VerdictType.ACCEPT_ALTERNATIVE,
}

# A non-approving verdict ends the trial without executing; the terminal status must reflect the
# verdict so the audit record (written downstream) captures the true outcome, not a generic DONE.
_TERMINAL_BY_VERDICT = {
    VerdictType.REJECT: ChangeStatus.REJECTED,
    VerdictType.WITHDRAW: ChangeStatus.WITHDRAWN,
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
        verdict_type: VerdictType | None = None
        if verdict_data is not None:
            verdict_type = Verdict.model_validate(verdict_data).type

        if verdict_type is not None and verdict_type not in _APPROVING:
            terminal = _TERMINAL_BY_VERDICT.get(verdict_type, ChangeStatus.DONE)
            return {"results": [], "status": terminal.value, "errors": errors}

        results: list[StepResult] = []
        for step in plan.steps:
            adapter = self._registry.get(step.capability.system)
            if adapter is None:
                logger.warning(
                    "step.failed",
                    extra={"step_id": step.step_id, "system": step.capability.system,
                           "error": "no adapter"},
                )
                metrics.increment("steps.failed")
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
                logger.warning(
                    "step.failed", extra={"step_id": result.step_id, "error": result.error}
                )
                metrics.increment("steps.failed")
                errors.append(f"step {result.step_id} failed: {result.error}")
            else:
                logger.info(
                    "step.ok", extra={"step_id": result.step_id, "status": result.status.value}
                )
                metrics.increment("steps.ok")

        had_failure = any(r.status is StepStatus.FAILED for r in results)
        status = ChangeStatus.FAILED if had_failure else ChangeStatus.DONE
        update: CourtState = {
            "results": [serialize(r) for r in results],
            "status": status.value,
            "errors": bound_errors(errors),
        }
        return update
