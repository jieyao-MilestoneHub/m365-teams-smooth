"""Verify node: the court reflects on its own execution before the record is sealed.

For a live run, each successful step's requested params are compared to the after-state the
adapter reported; the verifications land in the state for the audit record (and the result card
flags any mismatch). Dry runs predict without mutating, so there is nothing to verify and the
node passes through. Advisory only — a mismatch is recorded, never auto-corrected.
"""

from __future__ import annotations

import logging

from app.agent.state import CourtState, serialize
from app.domain import ExecutionPlan, RunMode, StepResult, StepStatus
from app.domain.verification import verify_effect
from app.observability import metrics

logger = logging.getLogger(__name__)


class VerifyNode:
    """Compares each live step's requested params to its reported after-state."""

    def __call__(self, state: CourtState) -> CourtState:
        # Default to dry-run when the field is somehow absent: skipping verification is safe,
        # failing the whole post-approval run over a missing key is not.
        if RunMode(state.get("run_mode", RunMode.DRY_RUN.value)) is not RunMode.LIVE:
            return {}
        options_data = state.get("options")
        if not isinstance(options_data, dict):
            return {}
        plan = ExecutionPlan.model_validate(options_data)
        params_by_step = {s.step_id: s.params for s in plan.steps}

        verifications = []
        for raw in state.get("results", []):
            result = StepResult.model_validate(raw)
            if result.status is not StepStatus.OK or result.after is None:
                continue
            params = params_by_step.get(result.step_id)
            if params is None:
                # A result for a step the reviewed plan does not contain: nothing legitimate to
                # compare against, and a vacuous "matched" would be misleading.
                logger.warning("verify.step_not_in_plan", extra={"step_id": result.step_id})
                continue
            verification = verify_effect(result.step_id, params, result.after)
            if not verification.matched:
                logger.warning(
                    "verify.mismatch",
                    extra={"step_id": result.step_id, "mismatches": verification.mismatches},
                )
                metrics.increment("verify.mismatches")
            verifications.append(serialize(verification))
        return {"verifications": verifications}
