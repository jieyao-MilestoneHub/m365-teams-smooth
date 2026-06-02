"""The three trials' rule packs, as validated data.

Expressed as ``RulePack`` literals (typed, no I/O) — declarative policy the engine interprets, not
branching code. They can be externalized to YAML later behind ``default_packs`` without touching the
policy node. Weights and approvers match docs/policy-and-quorum.md.
"""

from __future__ import annotations

from app.agent.policy_rules.models import (
    ApproverRule,
    MatchRules,
    QuorumRules,
    RiskBands,
    RiskFactorRule,
    RulePack,
    VerdictOptionRules,
)
from app.domain import ApproverRole, VerdictType

_STANDARD_BANDS = RiskBands(low=0, medium=30, high=60)

LAUNCH_SLIP = RulePack(
    id="launch_slip",
    match=MatchRules(
        any_action_capability=["github.update_milestone_due"],
        any_tag=["schedule.milestone_move"],
    ),
    risk_factors=[
        RiskFactorRule(id="milestone_move", when_tag="schedule.milestone_move", weight=40),
        RiskFactorRule(id="calendar_conflict", when_tag="schedule.calendar_conflict", weight=20),
        RiskFactorRule(id="planner_shift", when_tag="schedule.planner_shift", weight=10),
        RiskFactorRule(id="pending_announcement", when_tag="comms.pending_announcement", weight=10),
    ],
    risk_bands=_STANDARD_BANDS,
    quorum=QuorumRules(
        approvers=[
            ApproverRule(role=ApproverRole.ENG_LEAD, when_tag="schedule.milestone_move"),
            ApproverRule(role=ApproverRole.COMMS, when_tag="comms.pending_announcement"),
        ],
    ),
    verdict_options=VerdictOptionRules(
        default=[
            VerdictType.APPROVE,
            VerdictType.APPROVE_INTERNAL_ONLY,
            VerdictType.REQUEST_REVISION,
            VerdictType.REJECT,
        ],
        when_high_risk_internal=[
            VerdictType.APPROVE,
            VerdictType.APPROVE_INTERNAL_ONLY,
            VerdictType.REQUEST_REVISION,
            VerdictType.REJECT,
        ],
    ),
)

CUSTOMER_PROMISE = RulePack(
    id="customer_promise",
    match=MatchRules(
        any_tag=[
            "security.review_after_due_date",
            "github.blocking_issues_open",
            "crm.renewal_at_risk",
        ],
    ),
    risk_factors=[
        RiskFactorRule(id="blocking_issues", when_tag="github.blocking_issues_open", weight=30),
        RiskFactorRule(id="renewal_at_risk", when_tag="crm.renewal_at_risk", weight=20),
        RiskFactorRule(
            id="review_after_due_date",
            when_tag="security.review_after_due_date",
            weight=50,
            marks_unsafe=True,
        ),
    ],
    risk_bands=_STANDARD_BANDS,
    quorum=QuorumRules(
        approvers=[
            ApproverRule(
                role=ApproverRole.SECURITY_LEAD, when_tag="security.review_after_due_date"
            ),
            ApproverRule(role=ApproverRole.ACCOUNT_OWNER, when_tag="crm.renewal_at_risk"),
        ],
    ),
    verdict_options=VerdictOptionRules(
        default=[VerdictType.APPROVE, VerdictType.REQUEST_REVISION, VerdictType.REJECT],
        when_unsafe=[
            VerdictType.ACCEPT_ALTERNATIVE,
            VerdictType.REQUEST_REVISION,
            VerdictType.REJECT,
        ],
    ),
)

VENDOR_ACCESS = RulePack(
    id="vendor_access",
    match=MatchRules(
        any_action_capability=["sharepoint.grant_folder_permission"],
        any_tag=["access.overbroad_scope", "access.ambiguous_duration"],
    ),
    risk_factors=[
        RiskFactorRule(id="ambiguous_duration", when_tag="access.ambiguous_duration", weight=20),
        RiskFactorRule(
            id="overbroad_scope",
            when_tag="access.overbroad_scope",
            weight=40,
            marks_unsafe=True,
        ),
        RiskFactorRule(id="customer_data", when_tag="data.customer_data_present", weight=30),
    ],
    risk_bands=_STANDARD_BANDS,
    quorum=QuorumRules(
        approvers=[
            ApproverRule(role=ApproverRole.MANAGER, when_tag="access.overbroad_scope"),
            ApproverRule(role=ApproverRole.SECURITY_LEAD, when_tag="data.customer_data_present"),
        ],
    ),
    verdict_options=VerdictOptionRules(
        default=[VerdictType.APPROVE, VerdictType.REQUEST_REVISION, VerdictType.REJECT],
        when_unsafe=[
            VerdictType.ACCEPT_ALTERNATIVE,
            VerdictType.REQUEST_REVISION,
            VerdictType.REJECT,
        ],
    ),
)


def default_packs() -> list[RulePack]:
    """The rule packs governing the three trials."""
    return [LAUNCH_SLIP, CUSTOMER_PROMISE, VENDOR_ACCESS]
