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
    """An append-only record of a trial. Never updated; corrections are new records."""

    audit_id: str
    change_id: str
    thread_id: str
    run_mode: RunMode
    status: ChangeStatus
    trial: TrialRecord
    before_after: list[BeforeAfter] = Field(default_factory=list)
    rollback_hints: list[RollbackHint] = Field(default_factory=list)
    created_at: str
