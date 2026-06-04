"""The single business layer: submit a change, cast a verdict, read a trial or its status.

REST and MCP both delegate here — no business logic in the façades. Idempotency is enforced here so
both surfaces behave identically: a verdict is claimed in the ledger *before* the runner is resumed,
and a duplicate claim returns the recorded result instead of executing again. Low-risk changes that
need no approval are auto-resumed so they complete without a human verdict.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Literal, TypeVar
from uuid import uuid4

from pydantic import BaseModel

from app.agent.runner import CourtRunner
from app.agent.state import CourtState, initial_state, serialize
from app.domain import (
    ApprovalDecision,
    ApprovalEvent,
    ApproverRole,
    AuditRecord,
    Capability,
    Change,
    ChangeStatus,
    EffectVerification,
    ExecutionPlan,
    ImpactEvidence,
    PlanKind,
    Principal,
    Quorum,
    QuorumState,
    RiskResult,
    RunMode,
    StepResult,
    TrialRecord,
    Verdict,
    VerdictType,
    authorize_caster,
    evaluate_quorum,
)
from app.domain.errors import (
    InvalidRequestError,
    NotFoundError,
    SeparationOfDutiesError,
    UnauthorizedApproverError,
)
from app.observability import metrics
from app.ports.registry import IntegrationRegistry
from app.ports.repository import ApprovalLedger, AuditRepository, VerdictLedger
from app.services.approver_directory import ApproverDirectory
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
        approvals: ApprovalLedger | None = None,
        directory: ApproverDirectory | None = None,
        dry_run_default: bool = True,
        max_request_chars: int = 1000,
        id_factory: Callable[[], str] = lambda: uuid4().hex,
    ) -> None:
        self._runner = runner
        self._audit = audit_repo
        self._ledger = ledger
        self._registry = registry
        self._approvals = approvals
        self._directory = directory
        self._dry_run_default = dry_run_default
        self._max_request_chars = max_request_chars
        self._id = id_factory

    def capabilities(self) -> list[Capability]:
        """The merged capability catalog the court can act on (empty if no registry is wired)."""
        return self._registry.capabilities() if self._registry is not None else []

    def get_audit(self, audit_id: str) -> AuditRecord | None:
        """Fetch an append-only audit record by id."""
        return self._audit.get(audit_id)

    def submit_change(
        self,
        raw_request: str,
        *,
        source: str = "api",
        run_mode: RunMode | None = None,
        requester: Principal | None = None,
    ) -> TrialSummary:
        """Start a trial. It runs to the gate before execute.

        With a ``requester`` (identity-aware flow) the trial waits at the requester self-review gate
        (``AWAITING_REQUESTER_REVIEW``) — it is *not* auto-approved; the requester must
        :meth:`send_for_approval` or :meth:`withdraw_change`. Without a requester (legacy/local
        flow) a low-risk change is auto-approved so it completes without a human verdict.
        """
        # Boundary validation: a change request is a sentence or two; reject (never truncate)
        # anything else so the court only ever deliberates on exactly what was asked.
        if not raw_request.strip():
            raise InvalidRequestError("a change request is required")
        if len(raw_request) > self._max_request_chars:
            raise InvalidRequestError(
                f"change request exceeds {self._max_request_chars} characters"
            )
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
                requester=requester,
            ),
        )
        logger.info(
            "trial.submitted",
            extra={
                "thread_id": thread_id,
                "change_id": change_id,
                "source": source,
                "run_mode": mode.value,
                "requester": requester.key() if requester is not None else None,
            },
        )
        metrics.increment("trials.submitted")

        if requester is not None and self.approvals_configured():
            # Identity-aware flow: stamp the requester onto the change and hold for self-review.
            # Engages only when an approver directory exists — otherwise a held trial could never
            # be decided, so an unconfigured deployment keeps the legacy flow below.
            change = _model(state, "change", Change)
            update: CourtState = {"status": ChangeStatus.AWAITING_REQUESTER_REVIEW.value}
            if change is not None:
                change.requester = requester
                update["change"] = serialize(change)
            state = self._runner.update(thread_id, dict(update))
            return self._summary(thread_id, state)

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

    # --- Identity-aware approval routing (two-gate workflow + separation of duties) ---

    def send_for_approval(self, thread_id: str, *, actor: Principal, note: str) -> TrialSummary:
        """Requester self-review gate: send the proposal on for approval (a note is required).

        When the change needs no approver the requester carries the authority, so this executes.
        """
        trial = self._trial_or_raise(thread_id)
        self._require_is_requester(trial, actor, "send their change for approval")
        if not note.strip():
            raise ValueError("a note to the approver is required when sending for approval")
        self._append(thread_id, actor, ApprovalDecision.SEND, note=note)
        required = self._required_roles(trial)
        decision = evaluate_quorum(self._events(thread_id), required, self._policy(trial))
        if decision.state is QuorumState.SATISFIED:
            self._resume(thread_id, VerdictType.APPROVE, actor, self._plan_kind(trial))
        else:
            self._runner.update(thread_id, {"status": ChangeStatus.AWAITING_APPROVAL.value})
            self._require_ledger().mark_pending(thread_id, datetime.now(UTC).isoformat())
        logger.info("approval.sent", extra={"thread_id": thread_id, "actor": actor.key()})
        metrics.increment("approvals.sent")
        return self._summary(thread_id, self._runner.state(thread_id))

    def withdraw_change(self, thread_id: str, *, actor: Principal) -> TrialSummary:
        """Requester gives up before approval; terminal and audited, nothing executes."""
        trial = self._trial_or_raise(thread_id)
        self._require_is_requester(trial, actor, "withdraw their change")
        self._append(thread_id, actor, ApprovalDecision.WITHDRAW)
        self._resume(thread_id, VerdictType.WITHDRAW, actor, self._plan_kind(trial))
        state = self._runner.update(thread_id, {"status": ChangeStatus.WITHDRAWN.value})
        self._require_ledger().clear_pending(thread_id)
        logger.info("approval.withdrawn", extra={"thread_id": thread_id, "actor": actor.key()})
        metrics.increment("approvals.withdrawn")
        return self._summary(thread_id, state)

    def decide(
        self, thread_id: str, *, actor: Principal, approve: bool, note: str = ""
    ) -> TrialSummary:
        """Approver gate: an authorized approver (≠ requester) approves, or rejects with a note."""
        trial = self._trial_or_raise(thread_id)
        requester = trial.change.requester
        required = self._required_roles(trial)
        roles = self._directory.roles_for(actor) if self._directory is not None else set()
        auth = authorize_caster(actor, requester, required, roles)
        if not auth.allowed:
            if requester is not None and actor.same_as(requester):
                raise SeparationOfDutiesError(auth.reason)
            raise UnauthorizedApproverError(auth.reason)
        if not approve and not note.strip():
            raise ValueError("a note is required when rejecting")
        kind = ApprovalDecision.APPROVE if approve else ApprovalDecision.REJECT
        if not self._already(thread_id, actor, kind):
            self._append(thread_id, actor, kind, role=auth.role, note=note)
        decision = evaluate_quorum(self._events(thread_id), required, self._policy(trial))
        if decision.state is QuorumState.SATISFIED:
            self._resume(thread_id, VerdictType.APPROVE, actor, self._plan_kind(trial))
            self._require_ledger().clear_pending(thread_id)
        elif decision.state is QuorumState.REJECTED:
            self._resume(thread_id, VerdictType.REJECT, actor, self._plan_kind(trial))
            self._runner.update(thread_id, {"status": ChangeStatus.REJECTED.value})
            self._require_ledger().clear_pending(thread_id)
        logger.info(
            "approval.decided",
            extra={"thread_id": thread_id, "actor": actor.key(),
                   "approve": approve, "quorum": decision.state.value},
        )
        metrics.increment("approvals.decided")
        return self._summary(thread_id, self._runner.state(thread_id))

    def list_pending_approvals(self, principal: Principal) -> list[TrialSummary]:
        """Trials awaiting approval the principal may decide (authorized, not their own).

        Reads the pending index, so the cost scales with the open queue — never with the full
        trial history. The per-thread status check stays as a guard against a stale index entry.
        """
        ledger = self._require_ledger()
        pending: list[TrialSummary] = []
        for thread_id in ledger.pending_thread_ids():
            state = self._runner.state(thread_id)
            if str(state.get("status", "")) != ChangeStatus.AWAITING_APPROVAL.value:
                continue
            trial = self.get_trial(thread_id)
            if trial is None:
                continue
            requester = trial.change.requester
            if requester is not None and principal.same_as(requester):
                continue
            required = self._required_roles(trial)
            roles = self._directory.roles_for(principal) if self._directory is not None else set()
            if required and not (set(required) & roles):
                continue
            pending.append(self._summary(thread_id, state))
        return pending

    def approvals_configured(self) -> bool:
        """True when approval routing can be enforced (ledger present + a populated directory)."""
        return (
            self._approvals is not None
            and self._directory is not None
            and self._directory.configured()
        )

    def requester_note(self, thread_id: str) -> str:
        """The note the requester attached when sending for approval (empty when not sent)."""
        if self._approvals is None:
            return ""
        return self._approvals.first_note(thread_id, ApprovalDecision.SEND)

    def _trial_or_raise(self, thread_id: str) -> TrialRecord:
        trial = self.get_trial(thread_id)
        if trial is None:
            raise NotFoundError(f"trial '{thread_id}' not found")
        return trial

    @staticmethod
    def _require_is_requester(trial: TrialRecord, actor: Principal, action: str) -> None:
        requester = trial.change.requester
        if requester is None or not actor.same_as(requester):
            raise SeparationOfDutiesError(f"only the requester may {action}")

    def _require_ledger(self) -> ApprovalLedger:
        if self._approvals is None:
            raise RuntimeError("approval ledger is not configured")
        return self._approvals

    def _append(
        self,
        thread_id: str,
        actor: Principal,
        decision: ApprovalDecision,
        *,
        role: ApproverRole | None = None,
        note: str = "",
    ) -> None:
        self._require_ledger().append(
            ApprovalEvent(
                event_id=self._id(),
                thread_id=thread_id,
                actor=actor,
                decision=decision,
                role=role,
                note=note,
                at=datetime.now(UTC).isoformat(),
            )
        )

    def _events(self, thread_id: str) -> list[ApprovalEvent]:
        return self._require_ledger().list_for_thread(thread_id)

    def _already(self, thread_id: str, actor: Principal, decision: ApprovalDecision) -> bool:
        return any(
            e.actor.same_as(actor) and e.decision == decision for e in self._events(thread_id)
        )

    @staticmethod
    def _required_roles(trial: TrialRecord) -> list[ApproverRole]:
        return [a.role for a in trial.quorum.required_approvers] if trial.quorum else []

    @staticmethod
    def _policy(trial: TrialRecord) -> Literal["all", "any"]:
        return trial.quorum.policy if trial.quorum else "all"

    @staticmethod
    def _plan_kind(trial: TrialRecord) -> PlanKind:
        return trial.options.kind if trial.options else PlanKind.FEASIBLE

    def _resume(
        self, thread_id: str, verdict_type: VerdictType, actor: Principal, selected_plan: PlanKind
    ) -> None:
        verdict = Verdict(
            verdict_id=self._id(),
            type=verdict_type,
            selected_plan=selected_plan,
            actor=actor.upn or actor.key(),
            idempotency_key=f"{thread_id}:{verdict_type.value}",
        )
        self._runner.resume(thread_id, verdict)

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
            verifications=[
                EffectVerification.model_validate(v) for v in state.get("verifications", [])
            ],
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
