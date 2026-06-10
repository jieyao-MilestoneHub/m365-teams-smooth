"""The court graph state.

``CourtState`` holds only JSON-safe data — domain models are stored as ``model_dump(mode="json")``
dicts and rehydrated at node boundaries. This keeps the state losslessly serializable so a run can
be checkpointed at the verdict interrupt and resumed in a fresh process. Nodes return partial state
updates (LangGraph merges them); ``serialize`` builds those payloads from domain models.
"""

from __future__ import annotations

from typing import TypedDict

from pydantic import BaseModel

from app.domain import ChangeStatus, EvidenceItem, Principal, RunMode


class CourtState(TypedDict, total=False):
    """Serializable state threaded through the court nodes."""

    thread_id: str
    change_id: str
    raw_request: str
    source: str
    requester: dict[str, object]  # Principal (the authenticated opener)
    run_mode: str  # RunMode value

    change: dict[str, object]  # Change
    impact: dict[str, object]  # ImpactEvidence
    options: dict[str, object]  # ExecutionPlan
    risk: dict[str, object]  # RiskResult
    quorum: dict[str, object]  # Quorum
    verdict: dict[str, object]  # Verdict
    selected_plan: str  # PlanKind value

    results: list[dict[str, object]]  # StepResult dumps
    verifications: list[dict[str, object]]  # EffectVerification dumps (live runs only)
    deliberations: list[dict[str, object]]  # DeliberationEntry dumps (append-only reasoning trace)
    audit_id: str
    status: str  # ChangeStatus value
    errors: list[str]


def serialize(model: BaseModel) -> dict[str, object]:
    """Dump a domain model to a JSON-safe dict for storage in the state."""
    return model.model_dump(mode="json")


# State is fully serialized on every checkpoint (see CourtState docstring), so every accumulating
# field must stay bounded — an unbounded list inflates each subsequent checkpoint write and, for
# evidence, every downstream prompt (it is re-sent to the Defender).
MAX_ERRORS = 50
# One entry per node (a handful); the cap is a runaway guard, not an expected limit.
MAX_DELIBERATIONS = 50
# Deterministic core evidence is small; the cap guards the agentic-read tail. High-severity items
# (the decisive findings) are always kept.
MAX_EVIDENCE_ITEMS = 30


def bound_errors(errors: list[str]) -> list[str]:
    """Cap the error list a node writes back; the overflow is replaced by one marker entry."""
    if len(errors) <= MAX_ERRORS:
        return errors
    dropped = len(errors) - MAX_ERRORS
    return errors[:MAX_ERRORS] + [f"... {dropped} further errors truncated"]


def bound_deliberations(entries: list[dict[str, object]]) -> list[dict[str, object]]:
    """Cap the reasoning trace a node writes back, keeping the most recent entries."""
    return entries[-MAX_DELIBERATIONS:] if len(entries) > MAX_DELIBERATIONS else entries


def bound_evidence(items: list[EvidenceItem]) -> list[EvidenceItem]:
    """Cap the evidence a node writes back: keep every high-severity finding plus the most-recent
    remainder, and replace the overflow with one marker item."""
    if len(items) <= MAX_EVIDENCE_ITEMS:
        return items
    high = [i for i in items if i.severity == "high"]
    others = [i for i in items if i.severity != "high"]
    room = MAX_EVIDENCE_ITEMS - 1 - len(high)
    kept = (high + others[-room:]) if room > 0 else high[: MAX_EVIDENCE_ITEMS - 1]
    dropped = len(items) - len(kept)
    marker = EvidenceItem(
        system="court",
        kind="truncation",
        summary=f"... {dropped} further evidence item(s) truncated",
    )
    return [*kept, marker]


def initial_state(
    *,
    thread_id: str,
    change_id: str,
    raw_request: str,
    source: str,
    run_mode: RunMode,
    requester: Principal | None = None,
) -> CourtState:
    """Build the state a submitted change starts from."""
    state = CourtState(
        thread_id=thread_id,
        change_id=change_id,
        raw_request=raw_request,
        source=source,
        run_mode=run_mode.value,
        status=ChangeStatus.INTAKE.value,
        results=[],
        errors=[],
        deliberations=[],
    )
    if requester is not None:
        state["requester"] = requester.model_dump(mode="json")
    return state
