"""Audit node (Clerk): assemble the append-only trial record and persist it.

Builds the full TrialRecord (change, impact, options, risk, quorum, verdict, results) and appends
an immutable AuditRecord. Before/after snapshots and rollback hints are derived views on the
record (from the step results), so each fact is stored once. The clock and id factory are injected
so the record is deterministic under test.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

from app.agent.state import CourtState
from app.domain import (
    AuditRecord,
    Change,
    ChangeStatus,
    ExecutionPlan,
    ImpactEvidence,
    Quorum,
    RiskResult,
    RunMode,
    StepResult,
    TrialRecord,
    Verdict,
)
from app.ports.repository import AuditRepository


def _default_clock() -> str:
    return datetime.now(UTC).isoformat()


def _opt(state: CourtState, key: str) -> dict[str, object] | None:
    value = state.get(key)
    return value if isinstance(value, dict) else None


class AuditNode:
    """Writes the append-only audit record for the trial."""

    def __init__(
        self,
        audit_repo: AuditRepository,
        *,
        clock: Callable[[], str] = _default_clock,
        id_factory: Callable[[], str] = lambda: uuid4().hex,
    ) -> None:
        self._repo = audit_repo
        self._clock = clock
        self._id_factory = id_factory

    def __call__(self, state: CourtState) -> CourtState:
        change = Change.model_validate(state["change"])
        options_data = _opt(state, "options")
        options = ExecutionPlan.model_validate(options_data) if options_data else None
        results = [StepResult.model_validate(r) for r in state.get("results", [])]

        impact_data = _opt(state, "impact")
        risk_data = _opt(state, "risk")
        quorum_data = _opt(state, "quorum")
        verdict_data = _opt(state, "verdict")
        trial = TrialRecord(
            change=change,
            impact=ImpactEvidence.model_validate(impact_data) if impact_data else None,
            options=options,
            risk=RiskResult.model_validate(risk_data) if risk_data else None,
            quorum=Quorum.model_validate(quorum_data) if quorum_data else None,
            verdict=Verdict.model_validate(verdict_data) if verdict_data else None,
            results=results,
        )

        status = ChangeStatus(state.get("status", ChangeStatus.DONE.value))
        record = AuditRecord(
            audit_id=self._id_factory(),
            change_id=change.change_id,
            thread_id=state["thread_id"],
            run_mode=RunMode(state["run_mode"]),
            status=status,
            trial=trial,
            created_at=self._clock(),
        )
        self._repo.append(record)

        return {"audit_id": record.audit_id, "status": status.value}
