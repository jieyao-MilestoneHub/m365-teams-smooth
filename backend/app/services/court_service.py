"""The single business layer: submit a change, cast a verdict, read a trial or its status.

REST and MCP both delegate here — no business logic in the façades. Idempotency is enforced here so
both surfaces behave identically: a verdict is claimed in the ledger *before* the runner is resumed,
and a duplicate claim returns the recorded result instead of executing again. Every action is
identity-bound: the requester submits and confirms; when no approver is required their confirmation
executes the change, otherwise the quorum's authorized approvers decide.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Literal, TypeVar
from uuid import uuid4

from pydantic import BaseModel

from app.domain import (
    ApprovalDecision,
    ApprovalEvent,
    ApproverRole,
    AuditRecord,
    Capability,
    Change,
    ChangeStatus,
    Deliberation,
    DeliberationEntry,
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
    StepStatus,
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
from app.ports.notifier import ApprovalNotifier
from app.ports.registry import IntegrationRegistry
from app.ports.repository import ApprovalLedger, AuditRepository, VerdictLedger
from app.ports.run_event_sink import RunEventReader
from app.ports.runner import CourtRunnerPort, CourtState
from app.security.run_links import run_page_url, sign_thread, verify_thread
from app.services.approver_directory import ApproverDirectory
from app.services.dto import ApprovalTimelineEntry, CastResult, RunView, TrialSummary

logger = logging.getLogger(__name__)

_M = TypeVar("_M", bound=BaseModel)


def _model(state: CourtState, key: str, model: type[_M]) -> _M | None:
    value = state.get(key)
    return model.model_validate(value) if isinstance(value, dict) else None


class CourtService:
    """Orchestrates the court runner and the idempotency ledger behind a small API."""

    def __init__(
        self,
        runner: CourtRunnerPort,
        audit_repo: AuditRepository,
        ledger: VerdictLedger,
        *,
        registry: IntegrationRegistry | None = None,
        approvals: ApprovalLedger | None = None,
        directory: ApproverDirectory | None = None,
        notifier: ApprovalNotifier | None = None,
        run_events: RunEventReader | None = None,
        run_link_secret: str = "",
        public_base_url: str = "",
        ticket_url: str = "",
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
        self._notifier = notifier
        self._run_events = run_events
        self._run_link_secret = run_link_secret
        self._public_base_url = public_base_url
        self._ticket_url = ticket_url
        self._dry_run_default = dry_run_default
        self._max_request_chars = max_request_chars
        self._id = id_factory

    def attach_notifier(self, notifier: ApprovalNotifier) -> None:
        """Late-bind the approval notifier.

        The bot-chat card notifier reads trials through this service, so it can only be built
        after the service exists; the composition root constructs both and then attaches the
        composite here. Notifications stay best-effort either way.
        """
        self._notifier = notifier

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

        Every trial is identity-bound: the authenticated ``requester`` is required, and the trial
        waits at the requester self-review gate (``AWAITING_REQUESTER_REVIEW``). The requester then
        :meth:`send_for_approval` or :meth:`withdraw_change` — when the change needs no approver,
        sending executes it on the requester's own confirmation; otherwise the quorum's authorized
        approvers :meth:`decide`.

        ``run_mode=ANALYZE`` is an impact check: the trial records its evidence, plan, risk, and
        would-be approvers, then ends ``ANALYZED`` — nothing executes regardless of risk level,
        no approval round-trip starts, and the run cannot later be resumed into execution.
        """
        # Boundary validation: a change request is a sentence or two; reject (never truncate)
        # anything else so the court only ever deliberates on exactly what was asked. Identity is
        # part of the boundary — an approval gate without a requester cannot separate duties.
        if requester is None:
            raise InvalidRequestError("an authenticated requester is required to submit a change")
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
            change_id=change_id,
            raw_request=raw_request,
            source=source,
            run_mode=mode,
            requester=requester,
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

        if mode is RunMode.ANALYZE:
            # Analysis-only: stamp the requester for the record, then drive the run through the
            # skipping execute node to audit — it ends ANALYZED with no resumable next step, so
            # it never holds for review.
            change = _model(state, "change", Change)
            if change is not None:
                change.requester = requester
                self._runner.update(thread_id, {"change": change.model_dump(mode="json")})
            state = self._runner.advance(thread_id)
            self._notify_analyzed(thread_id, raw_request, requester)
            return self._summary(thread_id, state)

        # Stamp the requester onto the change and hold for self-review. Sending a no-approver
        # change executes it (the requester's own authority); quorum-bearing changes then wait
        # for their authorized approvers.
        change = _model(state, "change", Change)
        update: CourtState = {"status": ChangeStatus.AWAITING_REQUESTER_REVIEW.value}
        if change is not None:
            change.requester = requester
            update["change"] = change.model_dump(mode="json")
        state = self._runner.update(thread_id, dict(update))
        return self._summary(thread_id, state)

    def cast_verdict(
        self,
        thread_id: str,
        verdict_type: VerdictType,
        *,
        selected_plan: PlanKind = PlanKind.FEASIBLE,
        idempotency_key: str | None = None,
        actor: str = "reviewer",
        principal: Principal | None = None,
    ) -> CastResult:
        """Claim and apply a verdict; a duplicate claim returns the recorded result.

        Every caster is an authenticated ``principal`` passing the same authorization as
        :meth:`decide` — there is no identity-free verdict path, so separation of duties holds on
        every surface that can resume a trial.
        """
        self._reject_if_analysis_only(thread_id)
        if principal is None:
            raise UnauthorizedApproverError("authentication is required to cast a verdict")
        if self._directory is None:
            raise UnauthorizedApproverError("no approver directory is configured")
        trial = self._trial_or_raise(thread_id)
        requester = trial.change.requester
        auth = authorize_caster(
            principal,
            requester,
            self._required_roles(trial),
            self._directory.roles_for(principal),
        )
        if not auth.allowed:
            if requester is not None and principal.same_as(requester):
                raise SeparationOfDutiesError(auth.reason)
            raise UnauthorizedApproverError(auth.reason)
        actor = principal.upn or principal.key()
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
                thread_id=thread_id,
                execution_status=status,
                audit_id=audit_id,
                idempotent=True,
                run_url=self.run_link(thread_id),
                ticket_url=self._ticket_url or None,
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
        if self._approvals is not None:
            # A cast verdict is terminal however the trial got here — a trial that was sitting in
            # the approval queue must not linger there as a zombie row.
            self._approvals.clear_pending(thread_id)
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
        # The verdict gate is terminal however the trial got here — push the outcome to the
        # requester just like decide() does, so a trial never concludes silently. Best-effort:
        # _notify_decided swallows delivery failures, and the duplicate-claim path above never
        # reaches this, so a replay cannot re-notify.
        trial_after = self.get_trial(thread_id)
        if trial_after is not None:
            decider = principal if principal is not None else Principal(upn=actor)
            approved = verdict_type in (VerdictType.APPROVE, VerdictType.APPROVE_INTERNAL_ONLY)
            self._notify_decided(thread_id, trial_after, decider, approved=approved, note="")
        return CastResult(
            thread_id=thread_id,
            execution_status=str(state.get("status", "")),
            audit_id=audit_id if isinstance(audit_id, str) else None,
            run_url=self.run_link(thread_id),
            ticket_url=self._ticket_url or None,
        )

    def _reject_if_analysis_only(self, thread_id: str) -> None:
        """An analysis-only trial carries no executable intent — approval mutations are invalid."""
        if str(self._runner.state(thread_id).get("run_mode", "")) == RunMode.ANALYZE.value:
            raise InvalidRequestError(
                "trial is analysis-only — nothing can be approved or executed; "
                "submit a new change to act"
            )

    # --- Identity-aware approval routing (two-gate workflow + separation of duties) ---

    def send_for_approval(self, thread_id: str, *, actor: Principal, note: str) -> TrialSummary:
        """Requester self-review gate: send the proposal on for approval (a note is required).

        When the change needs no approver the requester carries the authority, so this executes.
        """
        self._reject_if_analysis_only(thread_id)
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
            self._notify_approval_requested(thread_id, trial, actor, note, required)
        logger.info("approval.sent", extra={"thread_id": thread_id, "actor": actor.key()})
        metrics.increment("approvals.sent")
        return self._summary(thread_id, self._runner.state(thread_id))

    def withdraw_change(self, thread_id: str, *, actor: Principal) -> TrialSummary:
        """Requester gives up before approval; terminal and audited, nothing executes."""
        self._reject_if_analysis_only(thread_id)
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
        self._reject_if_analysis_only(thread_id)
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
        # Record every required role this caster holds, not just the first: one authorized approver
        # who wears several hats (e.g. eng_lead AND comms) completes an all-roles quorum in a single
        # click. Distinct approvers each still contribute only their own role. Per-role dedup keeps
        # a repeat click idempotent; ``appended`` gates the resume so a re-click never re-executes.
        appended = False
        if approve:
            # Authorization guarantees the caster holds at least one required role, so this is
            # non-empty; record each so a multi-hat approver satisfies every role they cover.
            for role in (r for r in required if r in roles):
                if not self._already_role(thread_id, actor, role):
                    self._append(thread_id, actor, ApprovalDecision.APPROVE, role=role, note=note)
                    appended = True
        elif not self._already(thread_id, actor, ApprovalDecision.REJECT):
            self._append(thread_id, actor, ApprovalDecision.REJECT, role=auth.role, note=note)
            appended = True
        decision = evaluate_quorum(self._events(thread_id), required, self._policy(trial))
        if decision.state is QuorumState.SATISFIED and appended:
            self._resume(thread_id, VerdictType.APPROVE, actor, self._plan_kind(trial))
            self._require_ledger().clear_pending(thread_id)
            # Refetch so the notification carries what actually happened, not the pre-vote view.
            trial = self.get_trial(thread_id) or trial
            self._notify_decided(thread_id, trial, actor, approved=True, note=note)
        elif decision.state is QuorumState.REJECTED and appended:
            self._resume(thread_id, VerdictType.REJECT, actor, self._plan_kind(trial))
            self._runner.update(thread_id, {"status": ChangeStatus.REJECTED.value})
            self._require_ledger().clear_pending(thread_id)
            trial = self.get_trial(thread_id) or trial
            self._notify_decided(thread_id, trial, actor, approved=False, note=note)
        logger.info(
            "approval.decided",
            extra={"thread_id": thread_id, "actor": actor.key(),
                   "approve": approve, "quorum": decision.state.value},
        )
        metrics.increment("approvals.decided")
        return self._summary(thread_id, self._runner.state(thread_id))

    def acknowledge(self, thread_id: str, *, actor: Principal) -> TrialSummary:
        """Requester confirms the concluded outcome — the last sync point of the trial.

        Recorded as an append-only ACK event (visible alongside the audit trail) and pushed to the
        deciders, so requester and approver demonstrably agree on what the agent changed. Only the
        requester may acknowledge, only a concluded trial can be acknowledged, and a repeat ack is
        a no-op.
        """
        trial = self._trial_or_raise(thread_id)
        self._require_is_requester(trial, actor, "acknowledge their change's outcome")
        status = str(self._runner.state(thread_id).get("status", ""))
        if status not in (ChangeStatus.DONE.value, ChangeStatus.REJECTED.value):
            raise InvalidRequestError(
                f"trial is '{status}' — only a concluded trial can be acknowledged"
            )
        if not self._already(thread_id, actor, ApprovalDecision.ACK):
            self._append(thread_id, actor, ApprovalDecision.ACK)
            self._notify_acknowledged(thread_id, trial, actor)
            logger.info(
                "approval.acknowledged", extra={"thread_id": thread_id, "actor": actor.key()}
            )
            metrics.increment("approvals.acknowledged")
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

    def _already_role(self, thread_id: str, actor: Principal, role: ApproverRole) -> bool:
        """True when this actor has already approved in this specific role (per-role dedup)."""
        return any(
            e.actor.same_as(actor)
            and e.decision == ApprovalDecision.APPROVE
            and e.role == role
            for e in self._events(thread_id)
        )

    @staticmethod
    def _display(principal: Principal) -> str:
        """A human-friendly label for notification text — the display name, else the UPN/key.

        Only for the *text* of a notification; delivery still addresses the real UPN/oid.
        """
        return principal.display_name or principal.upn or principal.key()

    @staticmethod
    def _required_roles(trial: TrialRecord) -> list[ApproverRole]:
        return [a.role for a in trial.quorum.required_approvers] if trial.quorum else []

    @staticmethod
    def _policy(trial: TrialRecord) -> Literal["all", "any"]:
        return trial.quorum.policy if trial.quorum else "all"

    @staticmethod
    def _plan_kind(trial: TrialRecord) -> PlanKind:
        return trial.options.kind if trial.options else PlanKind.FEASIBLE

    def _notify_approval_requested(
        self,
        thread_id: str,
        trial: TrialRecord,
        actor: Principal,
        note: str,
        required: list[ApproverRole],
    ) -> None:
        """Best-effort push to everyone who can decide; never fails the send itself.

        Delivery is best-effort, but *having no one to deliver to* is a configuration dead-end —
        the trial sits in AWAITING_APPROVAL with no one able to decide. Both no-recipient paths
        therefore warn loudly with the reason instead of returning silently.
        """
        if self._notifier is None or self._directory is None:
            logger.warning(
                "notify.skipped",
                extra={
                    "thread_id": thread_id,
                    "event": "approval_requested",
                    "reason": "no approval notifier or approver directory is configured",
                },
            )
            metrics.increment("notify.skipped")
            return
        own_keys = {actor.oid.strip().lower(), actor.upn.strip().lower()} - {""}
        resolved = self._directory.identities_for(required)
        approvers = sorted(resolved - own_keys)
        if not approvers:
            reason = (
                "the required roles resolve only to the requester — configure a distinct approver"
                if resolved
                else "no identity is mapped for the required roles in APPROVER_DIRECTORY"
            )
            logger.warning(
                "notify.no_recipients",
                extra={
                    "thread_id": thread_id,
                    "event": "approval_requested",
                    "roles": [role.value for role in required],
                    "reason": reason,
                },
            )
            metrics.increment("notify.no_recipients")
            return
        try:
            self._notifier.approval_requested(
                thread_id=thread_id,
                title=trial.change.raw_request[:80],
                requester_upn=self._display(actor),  # text label; approver_upns address delivery
                approver_upns=approvers,
                note=note,
            )
            logger.info(
                "notify.sent",
                extra={
                    "thread_id": thread_id,
                    "event": "approval_requested",
                    "recipients": len(approvers),
                },
            )
            metrics.increment("notify.sent")
        except Exception as err:
            logger.warning(
                "notify.failed",
                extra={
                    "thread_id": thread_id,
                    "event": "approval_requested",
                    "reason": str(err)[:200],
                },
            )
            metrics.increment("notify.failed")

    def _notify_analyzed(self, thread_id: str, raw_request: str, requester: Principal) -> None:
        """Best-effort delivery of the analysis-only packet; never fails the submit itself."""
        if self._notifier is None:
            return
        try:
            self._notifier.analyzed(
                thread_id=thread_id,
                title=raw_request[:80],
                requester_upn=requester.upn or requester.key(),
            )
            logger.info(
                "notify.sent",
                extra={"thread_id": thread_id, "event": "analyzed"},
            )
            metrics.increment("notify.sent")
        except Exception as err:
            logger.warning(
                "notify.failed",
                extra={"thread_id": thread_id, "event": "analyzed", "reason": str(err)[:200]},
            )
            metrics.increment("notify.failed")

    @staticmethod
    def _outcome_summary(results: list[StepResult]) -> str:
        """One line of what execution actually did — plan-agnostic, built from step statuses."""
        if not results:
            return ""
        total = len(results)
        predicted = sum(1 for r in results if r.status is StepStatus.DRY_RUN)
        applied = sum(1 for r in results if r.status is StepStatus.OK)
        failed = [r for r in results if r.status is StepStatus.FAILED]
        summary = (
            f"{total} step(s) predicted (dry-run)"
            if predicted == total
            else f"{applied}/{total} step(s) applied"
        )
        if failed:
            first = failed[0]
            summary += f"; failed: {first.step_id}"
            if first.error:
                summary += f" ({first.error[:60]})"
        return summary

    def _notify_decided(
        self, thread_id: str, trial: TrialRecord, actor: Principal, *, approved: bool, note: str
    ) -> None:
        """Best-effort push of the outcome to the requester; never fails the decision itself."""
        if self._notifier is None:
            return
        requester = trial.change.requester
        if requester is None:
            return
        # The toast must say what happened, not just who decided — append the execution outcome.
        outcome = self._outcome_summary(trial.results) if approved else ""
        combined = " — ".join(part for part in (note.strip(), outcome) if part)
        try:
            self._notifier.decided(
                thread_id=thread_id,
                title=trial.change.raw_request[:80],
                requester_upn=requester.upn or requester.key(),  # delivery target — keep the UPN
                approved=approved,
                decider_upn=self._display(actor),  # text label only
                note=combined,
            )
            logger.info(
                "notify.sent",
                extra={"thread_id": thread_id, "event": "decided", "approved": approved},
            )
            metrics.increment("notify.sent")
        except Exception as err:
            logger.warning(
                "notify.failed",
                extra={"thread_id": thread_id, "event": "decided", "reason": str(err)[:200]},
            )
            metrics.increment("notify.failed")

    def _notify_acknowledged(self, thread_id: str, trial: TrialRecord, actor: Principal) -> None:
        """Best-effort push of the requester's ack to whoever decided; never fails the ack."""
        if self._notifier is None:
            return
        # Whoever actually decided: approval-ledger voters, plus the verdict's caster (the
        # cast_verdict path records no APPROVE event). Falls back to the directory.
        deciders = {
            (e.actor.upn or e.actor.key())
            for e in self._events(thread_id)
            if e.decision in (ApprovalDecision.APPROVE, ApprovalDecision.REJECT)
        }
        if trial.verdict is not None and trial.verdict.actor:
            deciders.add(trial.verdict.actor)
        own = {actor.oid.strip().lower(), actor.upn.strip().lower()} - {""}
        deciders = {d for d in deciders if d.strip().lower() not in own}
        if not deciders and self._directory is not None:
            deciders = self._directory.identities_for(self._required_roles(trial)) - own
        if not deciders:
            return
        try:
            self._notifier.acknowledged(
                thread_id=thread_id,
                title=trial.change.raw_request[:80],
                requester_upn=self._display(actor),  # text label; approver_upns address delivery
                approver_upns=sorted(deciders),
            )
            logger.info(
                "notify.sent",
                extra={
                    "thread_id": thread_id,
                    "event": "acknowledged",
                    "recipients": len(deciders),
                },
            )
            metrics.increment("notify.sent")
        except Exception as err:
            logger.warning(
                "notify.failed",
                extra={"thread_id": thread_id, "event": "acknowledged", "reason": str(err)[:300]},
            )
            metrics.increment("notify.failed")

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

    # --- Run page (read-only pipeline inspection) ---

    def run_page_enabled(self) -> bool:
        """True when run-page links can be signed and verified (a secret is configured)."""
        return bool(self._run_link_secret)

    def run_link(self, thread_id: str) -> str | None:
        """The signed run-page URL for a trial, or ``None`` when the run page is disabled."""
        if not self._run_link_secret:
            return None
        return run_page_url(self._public_base_url, thread_id, self._run_link_secret)

    def run_token(self, thread_id: str) -> str | None:
        """The bare token for a trial's run page (``None`` when disabled) — for tests/tools."""
        if not self._run_link_secret:
            return None
        return sign_thread(thread_id, self._run_link_secret)

    def verify_run_token(self, thread_id: str, token: str) -> bool:
        """Constant-time check that a presented token authorizes this thread's run page."""
        return verify_thread(thread_id, token, self._run_link_secret)

    def get_run_view(self, thread_id: str, *, after_seq: int = 0) -> RunView:
        """The run page's poll payload: new events past ``after_seq`` plus the current trial.

        Readable mid-run: the run-event log commits per event and the checkpointer saves after
        each node, so a poller watches the pipeline advance while the graph is still executing.
        """
        events = (
            self._run_events.list_after(thread_id, after_seq)
            if self._run_events is not None
            else []
        )
        state = self._runner.state(thread_id)
        trial = self.get_trial(thread_id)
        if trial is None and not events and not state.get("status"):
            raise NotFoundError(f"trial '{thread_id}' not found")
        approvals = (
            [
                ApprovalTimelineEntry(
                    decision=e.decision.value,
                    actor=self._display(e.actor),
                    role=e.role.value if e.role is not None else None,
                    note=e.note,
                    at=e.at,
                )
                for e in self._approvals.list_for_thread(thread_id)
            ]
            if self._approvals is not None
            else []
        )
        audit_id = state.get("audit_id")
        run_mode = state.get("run_mode")
        return RunView(
            summary=self._summary(thread_id, state),
            trial=trial,
            events=events,
            approvals=approvals,
            last_seq=max((e.seq for e in events), default=after_seq),
            run_mode=str(run_mode) if run_mode else None,
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
        entries = [DeliberationEntry.model_validate(d) for d in state.get("deliberations", [])]
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
            deliberation=Deliberation(entries=entries) if entries else None,
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
            acknowledged=(
                self._approvals is not None
                and any(e.decision is ApprovalDecision.ACK for e in self._events(thread_id))
            ),
            run_url=self.run_link(thread_id),
            ticket_url=self._ticket_url or None,
        )
