"""Execution plan: the steps the court proposes, and the result of running each."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.domain.capability import CapabilityRef
from app.domain.enums import PlanKind, StepStatus


class ExecutionStep(BaseModel):
    """One write action, bound to a capability. ``params`` must validate against its schema."""

    step_id: str
    capability: CapabilityRef
    params: dict[str, object] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)


class ExecutionPlan(BaseModel):
    """A feasible plan, or a safe alternative that supersedes the request."""

    kind: PlanKind
    steps: list[ExecutionStep] = Field(default_factory=list)
    rationale: str = ""
    supersedes_request: bool = False


class PredictedEffect(BaseModel):
    """What a DRY_RUN step would do; populated only in dry-run."""

    summary: str
    diff: dict[str, object] = Field(default_factory=dict)


class RollbackHint(BaseModel):
    """Advisory rollback guidance for a step. Never auto-executed."""

    step_id: str
    system: str
    instruction: str
    params: dict[str, object] = Field(default_factory=dict)


class StepResult(BaseModel):
    """The outcome of executing (or predicting) one step."""

    step_id: str
    status: StepStatus
    before: dict[str, object] | None = None
    after: dict[str, object] | None = None
    # A web link to the resource this step modified (e.g. the updated GitHub milestone), when the
    # adapter's after-state carries one — so a reviewer can open it from the run page or card.
    resource_url: str | None = None
    predicted: PredictedEffect | None = None
    error: str | None = None
    rollback: RollbackHint | None = None
