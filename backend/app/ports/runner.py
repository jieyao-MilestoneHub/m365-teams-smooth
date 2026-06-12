"""The court-runner port: drive a trial across the durable verdict interrupt.

Services depend on this contract only; the LangGraph-backed runner lives in ``app/agent``.
``CourtState`` is the JSON-safe state that crosses the boundary — domain models travel as
``model_dump(mode="json")`` dicts and are rehydrated by the caller.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import TypedDict

from app.domain import Principal, RunMode, Verdict


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


class CourtRunnerPort(ABC):
    """Starts, resumes, advances, patches, and reads a checkpointed court run."""

    @abstractmethod
    def start(
        self,
        thread_id: str,
        *,
        change_id: str,
        raw_request: str,
        source: str,
        run_mode: RunMode,
        requester: Principal | None = None,
    ) -> CourtState:
        """Build the initial state and run to the verdict gate; returns the checkpointed state."""

    @abstractmethod
    def resume(self, thread_id: str, verdict: Verdict) -> CourtState:
        """Record the verdict and resume past the gate. Idempotent once past the gate."""

    @abstractmethod
    def advance(self, thread_id: str) -> CourtState:
        """Drive a suspended run past the gate without a verdict (analysis-only runs)."""

    @abstractmethod
    def update(self, thread_id: str, values: Mapping[str, object]) -> CourtState:
        """Persist a partial state update on the suspended checkpoint without resuming."""

    @abstractmethod
    def state(self, thread_id: str) -> CourtState:
        """The current checkpointed state for a thread."""
