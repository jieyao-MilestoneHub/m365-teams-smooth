"""Derivations from the rule packs — the single source policy reacts to.

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


def grounding_queries(packs: list[RulePack]) -> dict[str, str]:
    """Subject → targeted grounding phrase, from each pack's scenario identity.

    The first pack claiming a subject wins, mirroring the policy node's first-match pack
    selection (and the loader's append semantics inherit that precedence).
    """
    queries: dict[str, str] = {}
    for pack in packs:
        if pack.grounding_query:
            for subject in pack.subjects:
                queries.setdefault(subject, pack.grounding_query)
    return queries
