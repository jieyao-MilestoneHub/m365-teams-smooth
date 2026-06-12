"""Tag sets derived from the rule packs — the single source policy reacts to.

Both functions read the same pack data the policy node interprets, so the agentic layer and the
generic planner can never drift from governance: a tag the packs don't know is a tag the system
ignores.
"""

from __future__ import annotations

from app.agent.policy_rules.models import RulePack


def marks_unsafe_tags(packs: list[RulePack]) -> frozenset[str]:
    """Every tag any pack's risk factors treat as marking the change unsafe."""
    return frozenset(
        rule.when_tag for pack in packs for rule in pack.risk_factors if rule.marks_unsafe
    )


def tag_vocabulary(packs: list[RulePack]) -> frozenset[str]:
    """Every tag policy can react to: risk factors, quorum approver rules, pack match rules."""
    return frozenset(
        [rule.when_tag for pack in packs for rule in pack.risk_factors]
        + [approver.when_tag for pack in packs for approver in pack.quorum.approvers]
        + [tag for pack in packs for tag in pack.match.any_tag]
    )
