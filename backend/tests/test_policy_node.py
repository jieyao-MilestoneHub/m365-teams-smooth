"""The policy node classifies risk deterministically, flags unsafe, and selects verdict options."""

from __future__ import annotations

from app.agent.nodes.policy import PolicyNode, evaluate_risk
from app.agent.policy_rules.models import (
    MatchRules,
    RiskFactorRule,
    RulePack,
    VerdictOptionRules,
)
from app.agent.state import CourtState, initial_state, serialize
from app.domain import (
    Change,
    ChangeStatus,
    EvidenceItem,
    GroundedFact,
    ImpactEvidence,
    RiskLevel,
    RiskResult,
    RunMode,
    VerdictType,
)

_PACK = RulePack(
    id="customer_promise",
    match=MatchRules(
        any_tag=[
            "github.blocking_issues_open",
            "crm.renewal_at_risk",
            "security.review_after_due_date",
        ]
    ),
    risk_factors=[
        RiskFactorRule(
            id="blocking",
            when_tag="github.blocking_issues_open",
            severity=RiskLevel.MEDIUM,
        ),
        RiskFactorRule(
            id="renewal", when_tag="crm.renewal_at_risk", severity=RiskLevel.LOW
        ),
        RiskFactorRule(
            id="review_after",
            when_tag="security.review_after_due_date",
            severity=RiskLevel.HIGH,
            marks_unsafe=True,
        ),
    ],
    verdict_options=VerdictOptionRules(
        default=[VerdictType.APPROVE, VerdictType.REJECT],
        when_unsafe=[VerdictType.ACCEPT_ALTERNATIVE, VerdictType.REJECT],
    ),
)


def test_evaluate_risk_takes_max_severity_and_flags_unsafe() -> None:
    tags = ["github.blocking_issues_open", "crm.renewal_at_risk", "security.review_after_due_date"]
    risk, unsafe = evaluate_risk(_PACK, tags)
    assert risk.level is RiskLevel.HIGH
    assert risk.requires_approval is True
    assert unsafe is True


def _state(tags: list[str], items: list[EvidenceItem] | None = None) -> CourtState:
    change = Change(change_id="c1", raw_request="promise GA", subject="sso-ga")
    state = initial_state(
        thread_id="t1",
        change_id="c1",
        raw_request="promise GA",
        source="t",
        run_mode=RunMode.DRY_RUN,
    )
    state["change"] = serialize(change)
    state["impact"] = serialize(ImpactEvidence(items=items or [], tags=tags))
    return state


def _grounded_item(*citations: str) -> EvidenceItem:
    return EvidenceItem(
        system="knowledge",
        kind="grounding",
        summary="governance facts",
        grounded=[GroundedFact(claim=f"clause {c}", source_id=c, citation=c) for c in citations],
    )


def test_unsafe_outcome_offers_accept_alternative_and_awaits_verdict() -> None:
    node = PolicyNode([_PACK])
    result = node(_state(["security.review_after_due_date"]))

    assert Change.model_validate(result["change"]).unsafe is True
    assert result["status"] == ChangeStatus.AWAITING_VERDICT.value
    options = result["quorum"]["verdict_options"]
    assert isinstance(options, list)
    types = {o["type"] for o in options}
    assert "accept_alternative" in types


def test_no_governing_pack_is_low_risk_and_proceeds() -> None:
    node = PolicyNode([_PACK])
    result = node(_state([]))  # no tags fire, pack has no match rules -> not selected
    assert result["status"] == ChangeStatus.EXECUTING.value


def test_fired_factors_carry_deduped_capped_citations() -> None:
    node = PolicyNode([_PACK])
    items = [
        _grounded_item("Policy A §1", "Policy A §1", "Policy B §3"),  # duplicate collapses
        _grounded_item("Policy C §2"),
    ]
    result = node(_state(["github.blocking_issues_open", "crm.renewal_at_risk"], items))

    risk = RiskResult.model_validate(result["risk"])
    assert len(risk.factors) == 2
    for factor in risk.factors:
        assert factor.grounded_citations == ["Policy A §1", "Policy B §3", "Policy C §2"]


def test_citations_are_advisory_only() -> None:
    node = PolicyNode([_PACK])
    tags = ["security.review_after_due_date"]
    bare = node(_state(tags))
    grounded = node(_state(tags, [_grounded_item("Policy A §1")]))

    bare_risk = RiskResult.model_validate(bare["risk"])
    grounded_risk = RiskResult.model_validate(grounded["risk"])
    assert grounded_risk.level is bare_risk.level
    assert grounded["quorum"] == bare["quorum"]
    assert grounded["status"] == bare["status"]
    assert bare_risk.factors[0].grounded_citations == []


def test_citation_cap_respected() -> None:
    node = PolicyNode([_PACK])
    items = [_grounded_item(*[f"Policy §{i}" for i in range(8)])]
    result = node(_state(["crm.renewal_at_risk"], items))

    risk = RiskResult.model_validate(result["risk"])
    assert len(risk.factors[0].grounded_citations) == 5
