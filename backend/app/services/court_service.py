"""The single business layer: submit a change, cast a verdict, read a trial or its status.

REST and MCP both delegate here — no business logic in the façades. Idempotency is enforced here so
both surfaces behave identically: a verdict is claimed in the ledger *before* the runner is resumed,
and a duplicate claim returns the recorded result instead of executing again. Low-risk changes that
need no approval are auto-resumed so they complete without a human verdict.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TypeVar
from uuid import uuid4

from pydantic import BaseModel

from app.agent.runner import CourtRunner
from app.agent.state import CourtState, initial_state
from app.domain import (
    AuditRecord,
    Capability,
    Change,
    ExecutionPlan,
    ImpactEvidence,
    PlanKind,
    Quorum,
    RiskResult,
    RunMode,
    StepResult,
    TrialRecord,
    Verdict,
    VerdictType,
)
from app.observability import metrics
from app.ports.registry import IntegrationRegistry
from app.ports.repository import AuditRepository, VerdictLedger
from app.services.dto import CastResult, TrialSummary

logger = logging.getLogger(__name__)

_M = TypeVar("_M", bound=BaseModel)


def _model(state: CourtState, key: str, model: type[_M]) -> _M | None:
    value = state.get(key)
    return model.model_validate(value) if isinstance(value, dict) else None


class CourtService:
    """Orchestrates the court runner and the idempotency ledger behind a small API."""

    def __init__(
        self,
        runner: CourtRunner,
        audit_repo: AuditRepository,
        ledger: VerdictLedger,
        *,
        registry: IntegrationRegistry | None = None,
        dry_run_default: bool = True,
        id_factory: Callable[[], str] = lambda: uuid4().hex,
    ) -> None:
        self._runner = runner
        self._audit = audit_repo
        self._ledger = ledger
        self._registry = registry
        self._dry_run_default = dry_run_default
        self._id = id_factory

    def capabilities(self) -> list[Capability]:
        """The merged capability catalog the court can act on (empty if no registry is wired)."""
        return self._registry.capabilities() if self._registry is not None else []

    def get_audit(self, audit_id: str) -> AuditRecord | None:
        """Fetch an append-only audit record by id."""
        return self._audit.get(audit_id)

    def submit_change(
        self, raw_request: str, *, source: str = "api", run_mode: RunMode | None = None
    ) -> TrialSummary:
        """Start a trial. It runs to the verdict gate; low-risk changes auto-complete."""
        mode = run_mode or (RunMode.DRY_RUN if self._dry_run_default else RunMode.LIVE)
        thread_id = self._id()
        change_id = self._id()
        state = self._runner.start(
            thread_id,
            initial_state(
                thread_id=thread_id,
                change_id=change_id,
                raw_request=raw_request,
                source=source,
                run_mode=mode,
            ),
        )
        logger.info(
            "trial.submitted",
            extra={
                "thread_id": thread_id,
                "change_id": change_id,
                "source": source,
                "run_mode": mode.value,
            },
        )
        metrics.increment("trials.submitted")

        risk = _model(state, "risk", RiskResult)
        needs_approval = isinstance(risk, RiskResult) and risk.requires_approval
        if self._runner.is_awaiting_verdict(thread_id) and not needs_approval:
            # No approval required: auto-approve so the change proceeds to execution.
            self.cast_verdict(thread_id, VerdictType.APPROVE, idempotency_key=f"auto:{thread_id}")
            state = self._runner.state(thread_id)

        return self._summary(thread_id, state)

    def cast_verdict(
        self,
        thread_id: str,
        verdict_type: VerdictType,
        *,
        selected_plan: PlanKind = PlanKind.FEASIBLE,
        idempotency_key: str | None = None,
        actor: str = "reviewer",
    ) -> CastResult:
        """Claim and apply a verdict; a duplicate claim returns the recorded result."""
        key = idempotency_key or f"{thread_id}:{verdict_type.value}:{selected_plan.value}"
        if not self._ledger.try_claim(thread_id, key):
            audit_id = self._ledger.result_for(thread_id, key)
            status = str(self._runner.state(thread_id).get("status", ""))
            logger.info(
                "verdict.duplicate",
                extra={"thread_id": thread_id, "idempotency_key": key, "audit_id": audit_id},
            )
            metrics.increment("verdicts.duplicate")
            return CastResult(
                thread_id=thread_id, status=status, audit_id=audit_id, idempotent=True
            )

        verdict = Verdict(
            verdict_id=self._id(),
            type=verdict_type,
            selected_plan=selected_plan,
            actor=actor,
            idempotency_key=key,
        )
        state = self._runner.resume(thread_id, verdict)
        audit_id = state.get("audit_id")
        if isinstance(audit_id, str):
            self._ledger.mark_completed(thread_id, key, audit_id)
        logger.info(
            "verdict.cast",
            extra={
                "thread_id": thread_id,
                "verdict_type": verdict_type.value,
                "selected_plan": selected_plan.value,
                "status": str(state.get("status", "")),
                "audit_id": audit_id if isinstance(audit_id, str) else None,
            },
        )
        metrics.increment("verdicts.cast")
        return CastResult(
            thread_id=thread_id,
            status=str(state.get("status", "")),
            audit_id=audit_id if isinstance(audit_id, str) else None,
        )

    def get_status(self, thread_id: str) -> str | None:
        status = self._runner.state(thread_id).get("status")
        return str(status) if status is not None else None

    def get_trial(self, thread_id: str) -> TrialRecord | None:
        state = self._runner.state(thread_id)
        change_data = state.get("change")
        if not isinstance(change_data, dict):
            return None
        return TrialRecord(
            change=Change.model_validate(change_data),
            impact=_model(state, "impact", ImpactEvidence),
            options=_model(state, "options", ExecutionPlan),
            risk=_model(state, "risk", RiskResult),
            quorum=_model(state, "quorum", Quorum),
            verdict=_model(state, "verdict", Verdict),
            results=[StepResult.model_validate(x) for x in state.get("results", [])],
        )

    def _summary(self, thread_id: str, state: CourtState) -> TrialSummary:
        change = _model(state, "change", Change)
        risk = _model(state, "risk", RiskResult)
        quorum = _model(state, "quorum", Quorum)
        options = _model(state, "options", ExecutionPlan)
        return TrialSummary(
            thread_id=thread_id,
            change_id=str(state.get("change_id", "")),
            status=str(state.get("status", "")),
            risk_level=risk.level.value if isinstance(risk, RiskResult) else None,
            requires_approval=isinstance(risk, RiskResult) and risk.requires_approval,
            unsafe=isinstance(change, Change) and change.unsafe,
            plan_kind=options.kind.value if isinstance(options, ExecutionPlan) else None,
            verdict_options=(
                [o.type.value for o in quorum.verdict_options] if isinstance(quorum, Quorum) else []
            ),
            errors=list(state.get("errors", [])),
        )
