"""Policy+quorum node: deterministic risk assessment and quorum derivation from a rule pack.

Risk is the highest severity among the factors whose tags fired (no summing, no thresholds); any
``marks_unsafe`` factor flags the change. Quorum (approvers + verdict options) is produced by an
injected resolver — the default derives verdict options only, while the tag-driven resolver also
derives the required approvers.
"""

from __future__ import annotations

from typing import Protocol

from app.agent.deliberate import Deliberator, OfflineDeliberator, record
from app.agent.policy_rules.models import UNGOVERNED_TAG, RulePack
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


def _grounding_citations(impact: ImpactEvidence, *, cap: int = 5) -> list[str]:
    """The trial's governance citations, deduped in evidence order and capped."""
    citations = (fact.citation for item in impact.items for fact in item.grounded if fact.citation)
    return list(dict.fromkeys(citations))[:cap]


def evaluate_risk(pack: RulePack, tags: list[str]) -> tuple[RiskResult, bool]:
    """Assess the fired factors into a RiskResult; also report whether the change is unsafe.

    The level is the most severe fired factor (max by severity rank), not a sum — a qualitative
    classification each factor is individually accountable for, with no thresholds to justify.
    """
    factors: list[RiskFactor] = []
    matched: list[str] = []
    unsafe = False
    level = RiskLevel.LOW
    for rule in pack.risk_factors:
        if rule.when_tag in tags:
            factors.append(
                RiskFactor(
                    id=rule.id,
                    label=rule.id,
                    severity=rule.severity,
                    evidence_tag=rule.when_tag,
                )
            )
            matched.append(rule.id)
            unsafe = unsafe or rule.marks_unsafe
            if rule.severity.rank > level.rank:
                level = rule.severity

    result = RiskResult(
        level=level,
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

    def __init__(
        self,
        packs: list[RulePack],
        resolver: QuorumResolver | None = None,
        deliberator: Deliberator | None = None,
        *,
        fallback_pack: RulePack | None = None,
    ) -> None:
        self._packs = packs
        self._resolver = resolver or DefaultQuorumResolver()
        self._deliberator = deliberator or OfflineDeliberator()
        self._fallback_pack = fallback_pack

    def __call__(self, state: CourtState) -> CourtState:
        change = Change.model_validate(state["change"])
        impact = ImpactEvidence.model_validate(state.get("impact", {"items": [], "tags": []}))
        tags = impact.tags

        pack = next((p for p in self._packs if _governs(p, change, tags)), None)
        if pack is None and self._fallback_pack is not None:
            # The policy floor: an ungoverned change is never waved through. The sentinel tag
            # joins the local fired set only (the recorded impact evidence is untouched), so the
            # fallback pack's factor and quorum rules fire like any other data-driven rule.
            pack = self._fallback_pack
            tags = [*tags, UNGOVERNED_TAG]
        if pack is None:
            risk = RiskResult(level=RiskLevel.LOW, requires_approval=False)
            quorum = Quorum()
        else:
            risk, unsafe = evaluate_risk(pack, tags)
            if unsafe:
                change.unsafe = True
            quorum = self._resolver.resolve(pack, tags, unsafe=unsafe, level=risk.level)
            # Attach the trial's governance citations to every fired factor — advisory context
            # only; the level, the unsafe flag, and quorum above are already final.
            citations = _grounding_citations(impact)
            if citations:
                for factor in risk.factors:
                    factor.grounded_citations = citations

        status = ChangeStatus.AWAITING_VERDICT if risk.requires_approval else ChangeStatus.EXECUTING

        approvers = ", ".join(a.role.value for a in quorum.required_approvers) or "none"
        factors = ", ".join(f"{f.label} ({f.severity.value})" for f in risk.factors) or "none"
        context = (
            f"Risk assessed {risk.level.value} (most severe fired factor) from factors: {factors}. "
            f"Approval {'required' if risk.requires_approval else 'not required'}; "
            f"approvers ({quorum.policy}): {approvers}. "
            f"{'Flagged unsafe.' if change.unsafe else ''}"
        ).strip()
        entry = self._deliberator.deliberate(node="policy", role="", context=context)

        update: CourtState = {
            "risk": serialize(risk),
            "quorum": serialize(quorum),
            "change": serialize(change),
            "status": status.value,
            "deliberations": record(state, entry),
        }
        return update
