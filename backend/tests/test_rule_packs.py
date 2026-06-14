"""The three rule packs classify each trial to the expected risk level, safety, and approvers."""

from __future__ import annotations

from app.agent.nodes.policy import RulePackQuorumResolver, evaluate_risk
from app.agent.policy_rules.packs import (
    CUSTOMER_PROMISE,
    LAUNCH_SLIP,
    VENDOR_ACCESS,
    default_packs,
)
from app.domain import ApproverRole, RiskLevel


def test_default_packs_cover_every_trial_subject() -> None:
    assert [p.id for p in default_packs()] == [
        "launch_slip",
        "customer_promise",
        "vendor_access",
        "meeting_actions",
        "weekly_report",
    ]


def test_launch_slip_needs_approval_but_is_not_unsafe() -> None:
    tags = [
        "schedule.milestone_move",
        "schedule.calendar_conflict",
        "schedule.planner_shift",
        "comms.pending_announcement",
    ]
    risk, unsafe = evaluate_risk(LAUNCH_SLIP, tags)
    assert risk.level is RiskLevel.MEDIUM
    assert unsafe is False
    roles = {a.role for a in RulePackQuorumResolver().resolve(
        LAUNCH_SLIP, tags, unsafe=unsafe, level=risk.level
    ).required_approvers}
    assert roles == {ApproverRole.ENG_LEAD, ApproverRole.COMMS}


def test_customer_promise_is_unsafe() -> None:
    tags = ["github.blocking_issues_open", "crm.renewal_at_risk", "security.review_after_due_date"]
    risk, unsafe = evaluate_risk(CUSTOMER_PROMISE, tags)
    assert risk.level is RiskLevel.HIGH
    assert unsafe is True


def test_vendor_access_is_unsafe_and_pulls_security_when_customer_data() -> None:
    tags = ["access.ambiguous_duration", "access.overbroad_scope", "data.customer_data_present"]
    risk, unsafe = evaluate_risk(VENDOR_ACCESS, tags)
    assert unsafe is True
    roles = {a.role for a in RulePackQuorumResolver().resolve(
        VENDOR_ACCESS, tags, unsafe=unsafe, level=risk.level
    ).required_approvers}
    assert roles == {ApproverRole.MANAGER, ApproverRole.SECURITY_LEAD}
