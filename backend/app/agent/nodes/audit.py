"""Audit node (Clerk): assemble the append-only trial record and persist it.

Builds the full TrialRecord (change, impact, options, risk, quorum, verdict, results) and appends
an immutable AuditRecord. Before/after snapshots and rollback hints are derived views on the
record (from the step results), so each fact is stored once. The clock and id factory are injected
so the record is deterministic under test.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

from app.agent.state import CourtState
from app.domain import (
    AuditRecord,
    Change,
    ChangeStatus,
    Deliberation,
    DeliberationEntry,
    EffectVerification,
    ExecutionPlan,
    ImpactEvidence,
    Quorum,
    RiskResult,
    RunMode,
    StepResult,
    TrialRecord,
    Verdict,
)
from app.ports.memory import MemoryPort, PrecedentRecord
from app.ports.repository import AuditRepository

logger = logging.getLogger(__name__)


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
        memory: MemoryPort | None = None,
        clock: Callable[[], str] = _default_clock,
        id_factory: Callable[[], str] = lambda: uuid4().hex,
    ) -> None:
        self._repo = audit_repo
        self._memory = memory
        self._clock = clock
        self._id_factory = id_factory

    def __call__(self, state: CourtState) -> CourtState:
        change = Change.model_validate(state["change"])
        options_data = _opt(state, "options")
        options = ExecutionPlan.model_validate(options_data) if options_data else None
        results = [StepResult.model_validate(r) for r in state.get("results", [])]
        verifications = [
            EffectVerification.model_validate(v) for v in state.get("verifications", [])
        ]

        impact_data = _opt(state, "impact")
        risk_data = _opt(state, "risk")
        quorum_data = _opt(state, "quorum")
        verdict_data = _opt(state, "verdict")
        entries = [DeliberationEntry.model_validate(d) for d in state.get("deliberations", [])]
        trial = TrialRecord(
            change=change,
            impact=ImpactEvidence.model_validate(impact_data) if impact_data else None,
            options=options,
            risk=RiskResult.model_validate(risk_data) if risk_data else None,
            quorum=Quorum.model_validate(quorum_data) if quorum_data else None,
            verdict=Verdict.model_validate(verdict_data) if verdict_data else None,
            results=results,
            verifications=verifications,
            deliberation=Deliberation(entries=entries) if entries else None,
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
        self._remember(record)

        return {"audit_id": record.audit_id, "status": status.value}

    def _remember(self, record: AuditRecord) -> None:
        """Summarize the ruling as a precedent. Best-effort: memory never blocks the audit."""
        if self._memory is None:
            return
        trial = record.trial
        try:
            self._memory.record(
                PrecedentRecord(
                    thread_id=record.thread_id,
                    subject=trial.change.subject or "",
                    tags=list(trial.impact.tags) if trial.impact else [],
                    raw_request=trial.change.raw_request,
                    verdict_type=trial.verdict.type.value if trial.verdict else "",
                    plan_kind=trial.options.kind.value if trial.options else "",
                    rationale=(trial.options.rationale if trial.options else "")[:300],
                    status=record.status.value,
                    created_at=record.created_at,
                )
            )
        except Exception as exc:  # noqa: BLE001 — the audit record is already safe
            logger.warning("precedent.record_failed", extra={"error": str(exc)})
