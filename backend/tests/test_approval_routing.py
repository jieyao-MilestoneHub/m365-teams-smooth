"""Service-level approval routing: requester self-review gate + approver separation of duties."""

from __future__ import annotations

import pytest

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
from app.domain.errors import SeparationOfDutiesError, UnauthorizedApproverError
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
