"""The rule-pack quorum resolver derives approvers from fired tags and options by outcome."""

from __future__ import annotations

from app.agent.nodes.policy import RulePackQuorumResolver
from app.agent.policy_rules.models import (
    ApproverRule,
    QuorumRules,
    RulePack,
    VerdictOptionRules,
)
from app.domain import ApproverRole, RiskLevel, VerdictType

_PACK = RulePack(
    id="customer_promise",
    quorum=QuorumRules(
        approvers=[
            ApproverRule(
                role=ApproverRole.SECURITY_LEAD, when_tag="security.review_after_due_date"
            ),
            ApproverRule(role=ApproverRole.ACCOUNT_OWNER, when_tag="crm.renewal_at_risk"),
        ],
    ),
    verdict_options=VerdictOptionRules(
        default=[VerdictType.APPROVE, VerdictType.REJECT],
        when_unsafe=[VerdictType.ACCEPT_ALTERNATIVE, VerdictType.REJECT],
    ),
)


def test_approvers_derived_from_fired_tags_only() -> None:
    resolver = RulePackQuorumResolver()
    quorum = resolver.resolve(
        _PACK,
        ["security.review_after_due_date"],  # only the security tag fired
        unsafe=True,
        level=RiskLevel.HIGH,
    )
    roles = {a.role for a in quorum.required_approvers}
    assert roles == {ApproverRole.SECURITY_LEAD}  # account_owner not required (its tag absent)
    assert quorum.required_approvers[0].derived_from_tag == "security.review_after_due_date"


def test_unsafe_outcome_offers_accept_alternative() -> None:
    resolver = RulePackQuorumResolver()
    quorum = resolver.resolve(
        _PACK,
        ["security.review_after_due_date", "crm.renewal_at_risk"],
        unsafe=True,
        level=RiskLevel.HIGH,
    )
    assert {a.role for a in quorum.required_approvers} == {
        ApproverRole.SECURITY_LEAD,
        ApproverRole.ACCOUNT_OWNER,
    }
    assert VerdictType.ACCEPT_ALTERNATIVE in {o.type for o in quorum.verdict_options}
