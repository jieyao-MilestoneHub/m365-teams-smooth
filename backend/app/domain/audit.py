"""Append-only audit record and the full trial it captures."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.domain.change import Change
from app.domain.enums import ChangeStatus, RunMode
from app.domain.impact import ImpactEvidence
from app.domain.plan import ExecutionPlan, RollbackHint, StepResult
from app.domain.quorum import Quorum
from app.domain.risk import RiskResult
from app.domain.verdict import Verdict


class BeforeAfter(BaseModel):
    """One before/after snapshot pair for an affected target."""

    system: str
    target: str
    before: dict[str, object] = Field(default_factory=dict)
    after: dict[str, object] = Field(default_factory=dict)


class TrialRecord(BaseModel):
    """The full reviewable trial: change, evidence, options, risk, quorum, verdict, results."""

    change: Change
    impact: ImpactEvidence | None = None
    options: ExecutionPlan | None = None
    risk: RiskResult | None = None
    quorum: Quorum | None = None
    verdict: Verdict | None = None
    results: list[StepResult] = Field(default_factory=list)


class AuditRecord(BaseModel):
    """An append-only record of a trial. Never updated; corrections are new records.

    The before/after snapshots and rollback hints are *views* derived from the trial's step
    results, not stored fields — the payload holds each fact once. (Old persisted payloads that
    carried them as fields still validate; the extras are ignored.)
    """

    audit_id: str
    change_id: str
    thread_id: str
    run_mode: RunMode
    status: ChangeStatus
    trial: TrialRecord
    created_at: str

    @property
    def before_after(self) -> list[BeforeAfter]:
        """One before/after pair per step result that captured a snapshot."""
        options = self.trial.options
        step_systems = {s.step_id: s.capability.system for s in (options.steps if options else [])}
        return [
            BeforeAfter(
                system=step_systems.get(r.step_id, "unknown"),
                target=r.step_id,
                before=r.before or {},
                after=r.after or {},
            )
            for r in self.trial.results
            if r.before is not None or r.after is not None
        ]

    @property
    def rollback_hints(self) -> list[RollbackHint]:
        """The advisory rollback hints the step results carry (never auto-executed)."""
        return [r.rollback for r in self.trial.results if r.rollback is not None]
