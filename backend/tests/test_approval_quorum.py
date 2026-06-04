"""Unit tests for the pure approval-routing core: separation of duties + quorum folding."""

from __future__ import annotations

from app.domain.approval import (
    ApprovalDecision,
    ApprovalEvent,
    QuorumState,
    authorize_caster,
    evaluate_quorum,
)
from app.domain.enums import ApproverRole
from app.domain.principal import Principal

REQUESTER = Principal(oid="req-1", upn="lowpriv@agentleague.onmicrosoft.com")
APPROVER = Principal(oid="app-1", upn="joel@agentleague.onmicrosoft.com")
ROLES = [ApproverRole.SECURITY_LEAD, ApproverRole.ACCOUNT_OWNER]


def _event(
    decision: ApprovalDecision,
    role: ApproverRole | None = None,
    actor: Principal = APPROVER,
) -> ApprovalEvent:
    return ApprovalEvent(event_id="e", thread_id="t", actor=actor, decision=decision, role=role)


# --- authorize_caster (separation of duties + authorization) ---

def test_requester_cannot_approve_own_change() -> None:
    d = authorize_caster(REQUESTER, REQUESTER, ROLES, [ApproverRole.SECURITY_LEAD])
    assert not d.allowed and "separation of duties" in d.reason


def test_caster_without_required_role_is_unauthorized() -> None:
    d = authorize_caster(APPROVER, REQUESTER, ROLES, [ApproverRole.COMMS])
    assert not d.allowed and "authorized approver" in d.reason


def test_authorized_approver_is_allowed_and_reports_role() -> None:
    held = [ApproverRole.ACCOUNT_OWNER, ApproverRole.COMMS]
    d = authorize_caster(APPROVER, REQUESTER, ROLES, held)
    assert d.allowed and d.role == ApproverRole.ACCOUNT_OWNER


def test_same_identity_by_upn_when_oid_absent_blocks() -> None:
    req = Principal(upn="joel@agentleague.onmicrosoft.com")
    d = authorize_caster(req, req, ROLES, [ApproverRole.SECURITY_LEAD])
    assert not d.allowed


# --- evaluate_quorum (folding events) ---

def test_quorum_pending_until_all_roles_under_all_policy() -> None:
    one = [_event(ApprovalDecision.APPROVE, ApproverRole.SECURITY_LEAD)]
    assert evaluate_quorum(one, ROLES, "all").state is QuorumState.PENDING
    both = one + [_event(ApprovalDecision.APPROVE, ApproverRole.ACCOUNT_OWNER)]
    decision = evaluate_quorum(both, ROLES, "all")
    assert decision.state is QuorumState.SATISFIED
    assert set(decision.approved_roles) == set(ROLES)


def test_any_policy_satisfied_on_first_required_role() -> None:
    one = [_event(ApprovalDecision.APPROVE, ApproverRole.SECURITY_LEAD)]
    assert evaluate_quorum(one, ROLES, "any").state is QuorumState.SATISFIED


def test_reject_is_terminal() -> None:
    events = [
        _event(ApprovalDecision.APPROVE, ApproverRole.SECURITY_LEAD),
        _event(ApprovalDecision.REJECT),
    ]
    assert evaluate_quorum(events, ROLES, "all").state is QuorumState.REJECTED


def test_withdraw_is_terminal() -> None:
    events = [_event(ApprovalDecision.WITHDRAW, actor=REQUESTER)]
    assert evaluate_quorum(events, ROLES, "all").state is QuorumState.WITHDRAWN


def test_no_required_roles_is_satisfied_immediately() -> None:
    assert evaluate_quorum([], [], "all").state is QuorumState.SATISFIED
