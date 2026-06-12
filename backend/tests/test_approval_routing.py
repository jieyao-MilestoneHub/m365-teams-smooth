"""Service-level approval routing: requester self-review gate + approver separation of duties."""

from __future__ import annotations

import pytest

from app.agent.nodes.impact import Gatherer
from app.agent.policy_rules.models import (
    ApproverRule,
    MatchRules,
    QuorumRules,
    RiskBands,
    RiskFactorRule,
    RulePack,
    VerdictOptionRules,
)
from app.config import Settings
from app.container import build_court_service
from app.domain import Change, ChangeStatus, ImpactEvidence, VerdictType
from app.domain.enums import ApproverRole
from app.domain.errors import (
    InvalidRequestError,
    SeparationOfDutiesError,
    UnauthorizedApproverError,
)
from app.domain.principal import Principal
from app.ports.knowledge import KnowledgePort
from app.ports.registry import IntegrationRegistry
from app.services.court_service import CourtService

REQUESTER = Principal(oid="low-1", upn="lowpriv@agentleague.onmicrosoft.com")
APPROVER = Principal(oid="joel-1", upn="joel@agentleague.onmicrosoft.com")
STRANGER = Principal(oid="x-1", upn="stranger@agentleague.onmicrosoft.com")

_PACK = RulePack(
    id="launch_slip",
    match=MatchRules(any_action_capability=["github.update_milestone_due"]),
    risk_factors=[RiskFactorRule(id="m", when_tag="schedule.milestone_move", weight=80)],
    risk_bands=RiskBands(low=0, medium=30, high=60),
    quorum=QuorumRules(
        approvers=[ApproverRule(role=ApproverRole.ENG_LEAD, when_tag="schedule.milestone_move")],
        policy="all",
    ),
    verdict_options=VerdictOptionRules(default=[VerdictType.APPROVE, VerdictType.REJECT]),
)


def _gatherer(
    change: Change, registry: IntegrationRegistry, knowledge: KnowledgePort, errors: list[str]
) -> ImpactEvidence:
    return ImpactEvidence(tags=["schedule.milestone_move"])


def _no_tag_gatherer(
    change: Change, registry: IntegrationRegistry, knowledge: KnowledgePort, errors: list[str]
) -> ImpactEvidence:
    """No impact tags → no risk factor fires → the quorum requires no approver."""
    return ImpactEvidence(tags=[])


def _service() -> CourtService:
    settings = Settings(
        force_all_mock=True,
        db_url="sqlite:///:memory:",
        dry_run_default=True,
        approver_directory="eng_lead:joel@agentleague.onmicrosoft.com",
    )
    return build_court_service(settings, gatherers={"launch": _gatherer}, packs=[_PACK])


_REQ = "slip the launch from 2026-06-10 to 2026-06-17"


def test_submit_with_requester_holds_for_self_review() -> None:
    service = _service()
    summary = service.submit_change(_REQ, requester=REQUESTER)
    assert summary.status == ChangeStatus.AWAITING_REQUESTER_REVIEW.value
    # Recorded requester travels onto the change for the audit trail.
    trial = service.get_trial(summary.thread_id)
    assert trial is not None and trial.change.requester is not None
    assert trial.change.requester.same_as(REQUESTER)


def test_submit_without_requester_is_rejected() -> None:
    # Identity is part of the boundary: there is no identity-free submission path.
    service = _service()
    with pytest.raises(InvalidRequestError):
        service.submit_change(_REQ)


def _no_directory_service(gatherer: Gatherer = _gatherer) -> CourtService:
    settings = Settings(force_all_mock=True, db_url="sqlite:///:memory:", dry_run_default=True)
    return build_court_service(settings, gatherers={"launch": gatherer}, packs=[_PACK])


def test_requester_without_directory_still_holds_for_self_review() -> None:
    # The requester gate engages even with no directory: identity is mandatory, and a
    # quorum-bearing change simply cannot be decided until a directory is configured.
    service = _no_directory_service()
    summary = service.submit_change(_REQ, requester=REQUESTER)
    assert summary.status == ChangeStatus.AWAITING_REQUESTER_REVIEW.value


def test_no_approver_change_executes_on_send_without_directory() -> None:
    # An empty quorum means the requester's own confirmation carries the authority — no
    # directory is needed for the routine path.
    service = _no_directory_service(_no_tag_gatherer)
    s = service.submit_change(_REQ, requester=REQUESTER)
    sent = service.send_for_approval(s.thread_id, actor=REQUESTER, note="routine, no approver")
    assert sent.status == ChangeStatus.DONE.value


def test_quorum_decision_without_directory_fails_authorization() -> None:
    # With approvers required but no directory, nobody can be authorized to decide.
    service = _no_directory_service()
    s = service.submit_change(_REQ, requester=REQUESTER)
    service.send_for_approval(s.thread_id, actor=REQUESTER, note="ready")
    with pytest.raises(UnauthorizedApproverError):
        service.decide(s.thread_id, actor=APPROVER, approve=True)


def test_requester_note_reads_back_the_send_note() -> None:
    service = _service()
    s = service.submit_change(_REQ, requester=REQUESTER)
    assert service.requester_note(s.thread_id) == ""
    service.send_for_approval(s.thread_id, actor=REQUESTER, note="ready for your call")
    assert service.requester_note(s.thread_id) == "ready for your call"


def test_requester_cannot_self_approve() -> None:
    service = _service()
    s = service.submit_change(_REQ, requester=REQUESTER)
    service.send_for_approval(s.thread_id, actor=REQUESTER, note="please review")
    with pytest.raises(SeparationOfDutiesError):
        service.decide(s.thread_id, actor=REQUESTER, approve=True)


def test_send_requires_note_then_routes_to_approval() -> None:
    service = _service()
    s = service.submit_change(_REQ, requester=REQUESTER)
    with pytest.raises(ValueError):
        service.send_for_approval(s.thread_id, actor=REQUESTER, note="   ")
    sent = service.send_for_approval(s.thread_id, actor=REQUESTER, note="ready for your call")
    assert sent.status == ChangeStatus.AWAITING_APPROVAL.value


def test_only_requester_may_send() -> None:
    service = _service()
    s = service.submit_change(_REQ, requester=REQUESTER)
    with pytest.raises(SeparationOfDutiesError):
        service.send_for_approval(s.thread_id, actor=APPROVER, note="not mine to send")


def test_unauthorized_approver_blocked() -> None:
    service = _service()
    s = service.submit_change(_REQ, requester=REQUESTER)
    service.send_for_approval(s.thread_id, actor=REQUESTER, note="ready")
    with pytest.raises(UnauthorizedApproverError):
        service.decide(s.thread_id, actor=STRANGER, approve=True)


def test_pending_queue_filters_by_identity() -> None:
    service = _service()
    s = service.submit_change(_REQ, requester=REQUESTER)
    service.send_for_approval(s.thread_id, actor=REQUESTER, note="ready")
    assert [t.thread_id for t in service.list_pending_approvals(APPROVER)] == [s.thread_id]
    assert service.list_pending_approvals(REQUESTER) == []


def test_authorized_approver_approves_and_executes() -> None:
    service = _service()
    s = service.submit_change(_REQ, requester=REQUESTER)
    service.send_for_approval(s.thread_id, actor=REQUESTER, note="ready")
    result = service.decide(s.thread_id, actor=APPROVER, approve=True)
    assert result.status == ChangeStatus.DONE.value
    # Idempotent: a repeat approve does not re-execute.
    again = service.decide(s.thread_id, actor=APPROVER, approve=True)
    assert again.status == ChangeStatus.DONE.value


# --- multi-role quorum: a single approver wearing several hats completes it in one click ---------

_TWO_ROLE_PACK = RulePack(
    id="launch_slip",
    match=MatchRules(any_action_capability=["github.update_milestone_due"]),
    risk_factors=[RiskFactorRule(id="m", when_tag="schedule.milestone_move", weight=80)],
    risk_bands=RiskBands(low=0, medium=30, high=60),
    quorum=QuorumRules(
        approvers=[
            ApproverRule(role=ApproverRole.ENG_LEAD, when_tag="schedule.milestone_move"),
            ApproverRule(role=ApproverRole.COMMS, when_tag="schedule.milestone_move"),
        ],
        policy="all",
    ),
    verdict_options=VerdictOptionRules(default=[VerdictType.APPROVE, VerdictType.REJECT]),
)


def _two_role_service(directory: str) -> CourtService:
    settings = Settings(
        force_all_mock=True,
        db_url="sqlite:///:memory:",
        dry_run_default=True,
        approver_directory=directory,
    )
    return build_court_service(
        settings, gatherers={"launch": _gatherer}, packs=[_TWO_ROLE_PACK]
    )


def test_single_approver_holding_all_roles_completes_quorum_in_one_click() -> None:
    # The deployed shape: one approver mapped to every role. A single approve must satisfy the
    # eng_lead AND comms quorum and execute — not deadlock at "pending".
    service = _two_role_service(
        "eng_lead:joel@agentleague.onmicrosoft.com,comms:joel@agentleague.onmicrosoft.com"
    )
    s = service.submit_change(_REQ, requester=REQUESTER)
    service.send_for_approval(s.thread_id, actor=REQUESTER, note="ready")
    result = service.decide(s.thread_id, actor=APPROVER, approve=True)
    assert result.status == ChangeStatus.DONE.value
    # Idempotent: a re-click does not re-execute.
    again = service.decide(s.thread_id, actor=APPROVER, approve=True)
    assert again.status == ChangeStatus.DONE.value


def test_two_distinct_approvers_each_supply_their_own_role() -> None:
    # Anti-collusion path is preserved: distinct people each hold one role and both must approve.
    approver2 = Principal(oid="comms-1", upn="comms@agentleague.onmicrosoft.com")
    service = _two_role_service(
        "eng_lead:joel@agentleague.onmicrosoft.com,comms:comms@agentleague.onmicrosoft.com"
    )
    s = service.submit_change(_REQ, requester=REQUESTER)
    service.send_for_approval(s.thread_id, actor=REQUESTER, note="ready")
    pending = service.decide(s.thread_id, actor=APPROVER, approve=True)  # eng_lead only
    assert pending.status == ChangeStatus.AWAITING_APPROVAL.value
    done = service.decide(s.thread_id, actor=approver2, approve=True)  # comms completes it
    assert done.status == ChangeStatus.DONE.value


def test_reject_requires_note_and_is_terminal() -> None:
    service = _service()
    s = service.submit_change(_REQ, requester=REQUESTER)
    service.send_for_approval(s.thread_id, actor=REQUESTER, note="ready")
    with pytest.raises(ValueError):
        service.decide(s.thread_id, actor=APPROVER, approve=False, note="")
    rejected = service.decide(s.thread_id, actor=APPROVER, approve=False, note="not yet")
    assert rejected.status == ChangeStatus.REJECTED.value


def test_withdraw_is_terminal_without_executing() -> None:
    service = _service()
    s = service.submit_change(_REQ, requester=REQUESTER)
    withdrawn = service.withdraw_change(s.thread_id, actor=REQUESTER)
    assert withdrawn.status == ChangeStatus.WITHDRAWN.value


# --- pending index lifecycle: the queue reads the index, never the full history ------------------


def _pending_ids(service: CourtService) -> list[str]:
    ledger = service._approvals  # white-box: assert the read-model
    assert ledger is not None
    return ledger.pending_thread_ids()


def test_send_marks_pending_and_terminal_decisions_clear_it() -> None:
    service = _service()
    s = service.submit_change(_REQ, requester=REQUESTER)
    assert _pending_ids(service) == []
    service.send_for_approval(s.thread_id, actor=REQUESTER, note="ready")
    assert _pending_ids(service) == [s.thread_id]
    service.decide(s.thread_id, actor=APPROVER, approve=True)
    assert _pending_ids(service) == []


def test_reject_and_withdraw_clear_the_pending_index() -> None:
    service = _service()
    rejected = service.submit_change(_REQ, requester=REQUESTER)
    service.send_for_approval(rejected.thread_id, actor=REQUESTER, note="ready")
    service.decide(rejected.thread_id, actor=APPROVER, approve=False, note="not yet")
    assert rejected.thread_id not in _pending_ids(service)

    withdrawn = service.submit_change(_REQ, requester=REQUESTER)
    service.withdraw_change(withdrawn.thread_id, actor=REQUESTER)
    assert withdrawn.thread_id not in _pending_ids(service)


def test_queue_scales_with_open_items_not_history() -> None:
    # Many finished trials, one open: the index (and so the queue scan) holds only the open one.
    service = _service()
    for _ in range(5):
        s = service.submit_change(_REQ, requester=REQUESTER)
        service.send_for_approval(s.thread_id, actor=REQUESTER, note="ready")
        service.decide(s.thread_id, actor=APPROVER, approve=True)
    open_one = service.submit_change(_REQ, requester=REQUESTER)
    service.send_for_approval(open_one.thread_id, actor=REQUESTER, note="ready")

    assert _pending_ids(service) == [open_one.thread_id]
    assert [t.thread_id for t in service.list_pending_approvals(APPROVER)] == [open_one.thread_id]


def test_requester_note_uses_the_send_event() -> None:
    service = _service()
    s = service.submit_change(_REQ, requester=REQUESTER)
    assert service.requester_note(s.thread_id) == ""
    service.send_for_approval(s.thread_id, actor=REQUESTER, note="first note")
    assert service.requester_note(s.thread_id) == "first note"


# --- cast_verdict must honour the same authorization as decide (no legacy bypass) ---


def test_requester_cannot_self_approve_via_cast_verdict() -> None:
    # The legacy verdict path must not bypass separation of duties for authenticated callers.
    service = _service()
    s = service.submit_change(_REQ, requester=REQUESTER)
    with pytest.raises(SeparationOfDutiesError):
        service.cast_verdict(s.thread_id, VerdictType.APPROVE, principal=REQUESTER)


def test_stranger_cannot_cast_verdict() -> None:
    service = _service()
    s = service.submit_change(_REQ, requester=REQUESTER)
    with pytest.raises(UnauthorizedApproverError):
        service.cast_verdict(s.thread_id, VerdictType.APPROVE, principal=STRANGER)


def test_directory_approver_can_cast_verdict_and_actor_is_the_identity() -> None:
    service = _service()
    s = service.submit_change(_REQ, requester=REQUESTER)
    service.send_for_approval(s.thread_id, actor=REQUESTER, note="please review")
    result = service.cast_verdict(s.thread_id, VerdictType.APPROVE, principal=APPROVER)
    assert result.verdict_recorded is True
    assert result.execution_status == "done"
    trial = service.get_trial(s.thread_id)
    assert trial is not None and trial.verdict is not None
    assert trial.verdict.actor == APPROVER.upn


def test_cast_verdict_without_principal_is_unauthorized() -> None:
    # There is no identity-free verdict path: an unauthenticated cast never resumes the run.
    service = _service()
    s = service.submit_change(_REQ, requester=REQUESTER)
    with pytest.raises(UnauthorizedApproverError):
        service.cast_verdict(s.thread_id, VerdictType.APPROVE)


def test_cast_verdict_without_directory_is_unauthorized() -> None:
    # Authentication alone is not enough — without a directory nobody holds a required role.
    service = _no_directory_service()
    s = service.submit_change(_REQ, requester=REQUESTER)
    with pytest.raises(UnauthorizedApproverError):
        service.cast_verdict(s.thread_id, VerdictType.APPROVE, principal=APPROVER)
