"""Policy+quorum node: deterministic risk scoring and quorum derivation from a rule pack.

Risk is the additive sum of the factors whose tags fired, banded into a level; any ``marks_unsafe``
factor flags the change. Quorum (approvers + verdict options) is produced by an injected resolver —
the default derives verdict options only; the tag-driven approver resolver lands in #86.
"""

from __future__ import annotations

from typing import Protocol

from app.agent.policy_rules.models import RulePack
from app.agent.state import CourtState, serialize
from app.domain import (
    Approver,
    Change,
    ChangeStatus,
    ImpactEvidence,
    Quorum,
    RiskFactor,
    RiskLevel,
    RiskResult,
    VerdictOption,
    VerdictType,
)


def evaluate_risk(pack: RulePack, tags: list[str]) -> tuple[RiskResult, bool]:
    """Score the fired factors into a RiskResult; also report whether the change is unsafe."""
    score = 0
    factors: list[RiskFactor] = []
    matched: list[str] = []
    unsafe = False
    for rule in pack.risk_factors:
        if rule.when_tag in tags:
            score += rule.weight
            factors.append(
                RiskFactor(
                    id=rule.id,
                    label=rule.id,
                    weight=rule.weight,
                    evidence_tag=rule.when_tag,
                )
            )
            matched.append(rule.id)
            unsafe = unsafe or rule.marks_unsafe

    bands = pack.risk_bands
    level = (
        RiskLevel.HIGH
        if score >= bands.high
        else RiskLevel.MEDIUM
        if score >= bands.medium
        else RiskLevel.LOW
    )
    result = RiskResult(
        level=level,
        score=score,
        factors=factors,
        requires_approval=level is not RiskLevel.LOW,
        matched_rule_ids=[pack.id, *matched],
    )
    return result, unsafe


class QuorumResolver(Protocol):
    """Derives the quorum (approvers + verdict options) from a pack and the fired tags."""

    def resolve(
        self, pack: RulePack, tags: list[str], *, unsafe: bool, level: RiskLevel
    ) -> Quorum: ...


def _select_options(pack: RulePack, *, unsafe: bool, level: RiskLevel) -> list[VerdictOption]:
    """Pick verdict options by outcome: unsafe → alternative; high → internal; else default."""
    options = pack.verdict_options
    if unsafe and options.when_unsafe:
        chosen = options.when_unsafe
    elif level is RiskLevel.HIGH and options.when_high_risk_internal:
        chosen = options.when_high_risk_internal
    else:
        chosen = options.default or [VerdictType.APPROVE, VerdictType.REJECT]
    return [VerdictOption(type=t, label=t.value) for t in chosen]


class DefaultQuorumResolver:
    """Selects verdict options by outcome, with no required approvers."""

    def resolve(self, pack: RulePack, tags: list[str], *, unsafe: bool, level: RiskLevel) -> Quorum:
        return Quorum(
            required_approvers=[],
            verdict_options=_select_options(pack, unsafe=unsafe, level=level),
            policy=pack.quorum.policy,
        )


class RulePackQuorumResolver:
    """Derives required approvers from the fired tags and selects verdict options by outcome."""

    def resolve(self, pack: RulePack, tags: list[str], *, unsafe: bool, level: RiskLevel) -> Quorum:
        approvers = [
            Approver(
                role=rule.role,
                reason=f"required because {rule.when_tag} is present",
                derived_from_tag=rule.when_tag,
            )
            for rule in pack.quorum.approvers
            if rule.when_tag in tags
        ]
        return Quorum(
            required_approvers=approvers,
            verdict_options=_select_options(pack, unsafe=unsafe, level=level),
            policy=pack.quorum.policy,
        )


def _governs(pack: RulePack, change: Change, tags: list[str]) -> bool:
    capabilities = {a.capability_name for a in change.requested_actions}
    by_capability = bool(
        pack.match.any_action_capability
        and capabilities.intersection(pack.match.any_action_capability)
    )
    by_tag = bool(pack.match.any_tag and set(tags).intersection(pack.match.any_tag))
    return by_capability or by_tag


class PolicyNode:
    """Selects the governing rule pack, scores risk, and derives the quorum."""

    def __init__(self, packs: list[RulePack], resolver: QuorumResolver | None = None) -> None:
        self._packs = packs
        self._resolver = resolver or DefaultQuorumResolver()

    def __call__(self, state: CourtState) -> CourtState:
        change = Change.model_validate(state["change"])
        impact = ImpactEvidence.model_validate(state.get("impact", {"items": [], "tags": []}))
        tags = impact.tags

        pack = next((p for p in self._packs if _governs(p, change, tags)), None)
        if pack is None:
            risk = RiskResult(level=RiskLevel.LOW, score=0, requires_approval=False)
            quorum = Quorum()
        else:
            risk, unsafe = evaluate_risk(pack, tags)
            if unsafe:
                change.unsafe = True
            quorum = self._resolver.resolve(pack, tags, unsafe=unsafe, level=risk.level)

        status = (
            ChangeStatus.AWAITING_VERDICT if risk.requires_approval else ChangeStatus.EXECUTING
        )
        update: CourtState = {
            "risk": serialize(risk),
            "quorum": serialize(quorum),
            "change": serialize(change),
            "status": status.value,
        }
        return update
