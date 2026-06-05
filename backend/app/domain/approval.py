"""Event-sourced approval: the append-only record of who did what to a trial, and the pure
functions that decide whether a caster may vote and whether a quorum is reached.

This module is the single home for the separation-of-duties and quorum rules. It imports no
framework and no persistence — the service appends :class:`ApprovalEvent` rows to a ledger and folds
them here. Time and ids are supplied by the caller so the domain stays deterministic and pure.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel

from app.domain.enums import ApproverRole
from app.domain.principal import Principal


class ApprovalDecision(StrEnum):
    """One action recorded against a trial's approval."""

    SEND = "send"  # requester sends the proposal on for approval (note required)
    WITHDRAW = "withdraw"  # requester gives up; terminal, nothing executes
    APPROVE = "approve"  # an authorized approver approves
    REJECT = "reject"  # an authorized approver rejects (note required)
    ACK = "ack"  # requester confirms they saw the concluded outcome (post-execution, no effect)


class ApprovalEvent(BaseModel):
    """An append-only record of one approval action. Never mutated."""

    event_id: str
    thread_id: str
    actor: Principal
    decision: ApprovalDecision
    role: ApproverRole | None = None  # required role the approver acted under (None for requester)
    note: str = ""
    at: str = ""  # ISO-8601, stamped at the service edge


class QuorumState(StrEnum):
    """The aggregate outcome of folding a trial's approval events."""

    PENDING = "pending"  # still awaiting the required approvals
    SATISFIED = "satisfied"  # quorum reached — the trial may execute
    REJECTED = "rejected"  # an approver rejected
    WITHDRAWN = "withdrawn"  # the requester withdrew


@dataclass(frozen=True)
class AuthDecision:
    """Whether a caster is allowed to vote, and (if so) the role they satisfy."""

    allowed: bool
    reason: str = ""
    role: ApproverRole | None = None


@dataclass(frozen=True)
class QuorumDecision:
    """The folded quorum state and the roles that have approved so far."""

    state: QuorumState
    approved_roles: tuple[ApproverRole, ...] = ()
    reason: str = ""


def authorize_caster(
    actor: Principal,
    requester: Principal | None,
    required_roles: Sequence[ApproverRole],
    actor_roles: Iterable[ApproverRole],
) -> AuthDecision:
    """Decide whether ``actor`` may cast a verdict (separation of duties + authorization).

    ``actor_roles`` is the set of approver roles the directory resolved for the caster. The caster
    cannot vote on their own request, and must hold at least one of the required roles.
    """
    if actor.same_as(requester):
        return AuthDecision(False, "separation of duties: requester cannot self-approve")
    held = set(actor_roles)
    satisfied = [role for role in required_roles if role in held]
    if not satisfied:
        return AuthDecision(False, "not an authorized approver for any required role")
    return AuthDecision(True, role=satisfied[0])


def evaluate_quorum(
    events: Sequence[ApprovalEvent],
    required_roles: Sequence[ApproverRole],
    policy: Literal["all", "any"],
) -> QuorumDecision:
    """Fold approval events into the quorum state.

    Withdraw and reject are terminal-negative and take precedence. Otherwise the approved roles are
    compared against the required roles under ``policy`` (``all`` = every required role approved,
    ``any`` = at least one). An empty requirement is satisfied immediately.
    """
    decisions = [e.decision for e in events]
    if ApprovalDecision.WITHDRAW in decisions:
        return QuorumDecision(QuorumState.WITHDRAWN, reason="withdrawn by requester")
    if ApprovalDecision.REJECT in decisions:
        return QuorumDecision(QuorumState.REJECTED, reason="rejected by approver")

    approved = tuple(
        {e.role for e in events if e.decision == ApprovalDecision.APPROVE and e.role is not None}
    )
    required = set(required_roles)
    if not required:
        return QuorumDecision(QuorumState.SATISFIED, approved)
    reached = bool(required & set(approved)) if policy == "any" else required <= set(approved)
    return QuorumDecision(QuorumState.SATISFIED if reached else QuorumState.PENDING, approved)
