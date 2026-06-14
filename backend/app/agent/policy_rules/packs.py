"""The three trials' rule packs, as validated data.

Expressed as ``RulePack`` literals (typed, no I/O) — declarative policy the engine interprets, not
branching code. They can be externalized to YAML later behind ``default_packs`` without touching the
policy node.
"""

from __future__ import annotations

from app.agent.policy_rules.models import (
    UNGOVERNED_TAG,
    ApproverRule,
    MatchRules,
    QuorumRules,
    RiskFactorRule,
    RulePack,
    VerdictOptionRules,
)
from app.domain import ApproverRole, RiskLevel, VerdictType

# Each pack's grounding_query is tuned so the knowledge base ranks the intended governance policy
# above its adversarial near-misses — validated by backend/scripts/eval_retrieval.py. Grounding is
# citations only: it never produces tags and never affects risk, quorum, or the verdict.

LAUNCH_SLIP = RulePack(
    id="launch_slip",
    subjects=["launch"],
    grounding_query="schedule change controlled coordinated milestone date",
    match=MatchRules(
        any_action_capability=["github.update_milestone_due"],
        any_tag=["schedule.milestone_move", "schedule.contractual_breach_risk"],
    ),
    risk_factors=[
        RiskFactorRule(
            id="milestone_move", when_tag="schedule.milestone_move", severity=RiskLevel.MEDIUM
        ),
        RiskFactorRule(
            id="calendar_conflict", when_tag="schedule.calendar_conflict", severity=RiskLevel.LOW
        ),
        RiskFactorRule(
            id="planner_shift", when_tag="schedule.planner_shift", severity=RiskLevel.LOW
        ),
        RiskFactorRule(
            id="pending_announcement",
            when_tag="comms.pending_announcement",
            severity=RiskLevel.LOW,
        ),
        RiskFactorRule(
            id="target_date_conflict",
            when_tag="schedule.target_date_conflict",
            severity=RiskLevel.HIGH,
            marks_unsafe=True,
        ),
        # A latent contractual/freeze/dependency breach the cross-system check derived: graver than
        # a visible calendar clash, because no single system reveals it.
        RiskFactorRule(
            id="contractual_breach_risk",
            when_tag="schedule.contractual_breach_risk",
            severity=RiskLevel.HIGH,
            marks_unsafe=True,
        ),
    ],
    quorum=QuorumRules(
        approvers=[
            ApproverRule(role=ApproverRole.ENG_LEAD, when_tag="schedule.milestone_move"),
            ApproverRule(role=ApproverRole.COMMS, when_tag="comms.pending_announcement"),
            # A contractual breach is a commercial matter: the account owner must sign off.
            ApproverRule(
                role=ApproverRole.ACCOUNT_OWNER, when_tag="schedule.contractual_breach_risk"
            ),
        ],
        # Both the engineering and comms leads are surfaced as stakeholders, but a single
        # sign-off from either suffices to reach quorum (need = 1).
        policy="any",
    ),
    verdict_options=VerdictOptionRules(
        default=[
            VerdictType.APPROVE,
            VerdictType.APPROVE_INTERNAL_ONLY,
            VerdictType.REQUEST_REVISION,
            VerdictType.REJECT,
        ],
        when_unsafe=[
            VerdictType.ACCEPT_ALTERNATIVE,
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
    subjects=["sso-ga"],
    grounding_query="SSO GA promise security review sign-off",
    match=MatchRules(
        any_tag=[
            "security.review_after_due_date",
            "github.blocking_issues_open",
            "crm.renewal_at_risk",
        ],
    ),
    risk_factors=[
        RiskFactorRule(
            id="blocking_issues", when_tag="github.blocking_issues_open", severity=RiskLevel.MEDIUM
        ),
        RiskFactorRule(
            id="renewal_at_risk", when_tag="crm.renewal_at_risk", severity=RiskLevel.LOW
        ),
        RiskFactorRule(
            id="review_after_due_date",
            when_tag="security.review_after_due_date",
            severity=RiskLevel.HIGH,
            marks_unsafe=True,
        ),
    ],
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
    subjects=["project-access"],
    grounding_query="vendor access least privilege scope expiry",
    match=MatchRules(
        any_action_capability=["sharepoint.grant_folder_permission"],
        any_tag=["access.overbroad_scope", "access.ambiguous_duration"],
    ),
    risk_factors=[
        RiskFactorRule(
            id="ambiguous_duration", when_tag="access.ambiguous_duration", severity=RiskLevel.LOW
        ),
        RiskFactorRule(
            id="overbroad_scope",
            when_tag="access.overbroad_scope",
            severity=RiskLevel.HIGH,
            marks_unsafe=True,
        ),
        RiskFactorRule(
            id="customer_data", when_tag="data.customer_data_present", severity=RiskLevel.MEDIUM
        ),
    ],
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


MEETING_ACTIONS = RulePack(
    id="meeting_actions",
    subjects=["meeting-actions"],
    grounding_query="meeting follow-through action item owner due date accountability",
    match=MatchRules(
        any_action_capability=["planner.create_task"],
        any_tag=["meeting.action_items_found"],
    ),
    risk_factors=[
        RiskFactorRule(
            id="action_items_found",
            when_tag="meeting.action_items_found",
            severity=RiskLevel.LOW,
        ),
    ],
    # Internal task tracking carries the requester's own authority: low risk, no approver —
    # the requester's confirmation at the review gate is what executes it.
    quorum=QuorumRules(approvers=[]),
    verdict_options=VerdictOptionRules(
        default=[VerdictType.APPROVE, VerdictType.REQUEST_REVISION, VerdictType.REJECT],
    ),
)


WEEKLY_REPORT = RulePack(
    id="weekly_report",
    subjects=["weekly-report"],
    grounding_query="status reporting weekly cadence single source of record",
    match=MatchRules(
        any_action_capability=["teams.post_message"],
        any_tag=["report.activity_collected"],
    ),
    risk_factors=[
        RiskFactorRule(
            id="activity_collected", when_tag="report.activity_collected", severity=RiskLevel.LOW
        ),
    ],
    # Posting an internal status summary is the requester's own authority: low risk, no approver.
    quorum=QuorumRules(approvers=[]),
    verdict_options=VerdictOptionRules(
        default=[VerdictType.APPROVE, VerdictType.REQUEST_REVISION, VerdictType.REJECT],
    ),
)


# The policy floor: engaged only as the injected fallback when NO pack governs a change. The
# sentinel tag fires its factor (medium severity, approval required) and convenes the manager —
# "unknown" means "ask a human", never "free pass". It never matches by itself.
UNGOVERNED = RulePack(
    id="ungoverned",
    match=MatchRules(),
    risk_factors=[
        RiskFactorRule(
            id="ungoverned_change", when_tag=UNGOVERNED_TAG, severity=RiskLevel.MEDIUM
        ),
    ],
    quorum=QuorumRules(
        approvers=[ApproverRule(role=ApproverRole.MANAGER, when_tag=UNGOVERNED_TAG)],
    ),
    verdict_options=VerdictOptionRules(
        default=[VerdictType.APPROVE, VerdictType.REQUEST_REVISION, VerdictType.REJECT],
    ),
)


def default_packs() -> list[RulePack]:
    """The rule packs governing the trials."""
    return [LAUNCH_SLIP, CUSTOMER_PROMISE, VENDOR_ACCESS, MEETING_ACTIONS, WEEKLY_REPORT]
