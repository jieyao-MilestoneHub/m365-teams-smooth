"""The court graph state.

``CourtState`` holds only JSON-safe data — domain models are stored as ``model_dump(mode="json")``
dicts and rehydrated at node boundaries. This keeps the state losslessly serializable so a run can
be checkpointed at the verdict interrupt and resumed in a fresh process. Nodes return partial state
updates (LangGraph merges them); ``serialize`` builds those payloads from domain models.
"""

from __future__ import annotations

from typing import TypedDict

from pydantic import BaseModel

from app.domain import ChangeStatus, RunMode


class CourtState(TypedDict, total=False):
    """Serializable state threaded through the court nodes."""

    thread_id: str
    change_id: str
    raw_request: str
    source: str
    run_mode: str  # RunMode value

    change: dict[str, object]  # Change
    impact: dict[str, object]  # ImpactEvidence
    options: dict[str, object]  # ExecutionPlan
    risk: dict[str, object]  # RiskResult
    quorum: dict[str, object]  # Quorum
    verdict: dict[str, object]  # Verdict
    selected_plan: str  # PlanKind value

    results: list[dict[str, object]]  # StepResult dumps
    audit_id: str
    status: str  # ChangeStatus value
    errors: list[str]


def serialize(model: BaseModel) -> dict[str, object]:
    """Dump a domain model to a JSON-safe dict for storage in the state."""
    return model.model_dump(mode="json")


def initial_state(
    *,
    thread_id: str,
    change_id: str,
    raw_request: str,
    source: str,
    run_mode: RunMode,
) -> CourtState:
    """Build the state a submitted change starts from."""
    return CourtState(
        thread_id=thread_id,
        change_id=change_id,
        raw_request=raw_request,
        source=source,
        run_mode=run_mode.value,
        status=ChangeStatus.INTAKE.value,
        results=[],
        errors=[],
    )
