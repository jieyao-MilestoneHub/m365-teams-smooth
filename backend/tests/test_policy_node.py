"""The policy node scores risk deterministically, flags unsafe, and selects verdict options."""

from __future__ import annotations

from app.agent.nodes.policy import PolicyNode, evaluate_risk
from app.agent.policy_rules.models import (
    MatchRules,
    RiskBands,
    RiskFactorRule,
    RulePack,
    VerdictOptionRules,
)
from app.agent.state import CourtState, initial_state, serialize
from app.domain import (
    Change,
    ChangeStatus,
    ImpactEvidence,
    RiskLevel,
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
        RiskFactorRule(id="blocking", when_tag="github.blocking_issues_open", weight=30),
        RiskFactorRule(id="renewal", when_tag="crm.renewal_at_risk", weight=20),
        RiskFactorRule(
            id="review_after",
            when_tag="security.review_after_due_date",
            weight=50,
            marks_unsafe=True,
        ),
    ],
    risk_bands=RiskBands(low=0, medium=30, high=60),
    verdict_options=VerdictOptionRules(
        default=[VerdictType.APPROVE, VerdictType.REJECT],
        when_unsafe=[VerdictType.ACCEPT_ALTERNATIVE, VerdictType.REJECT],
    ),
)


def test_evaluate_risk_sums_fired_factors_and_flags_unsafe() -> None:
    tags = ["github.blocking_issues_open", "crm.renewal_at_risk", "security.review_after_due_date"]
    risk, unsafe = evaluate_risk(_PACK, tags)
    assert risk.score == 100
    assert risk.level is RiskLevel.HIGH
    assert risk.requires_approval is True
    assert unsafe is True


def _state(tags: list[str]) -> CourtState:
    change = Change(change_id="c1", raw_request="promise GA", subject="sso-ga")
    state = initial_state(
        thread_id="t1",
        change_id="c1",
        raw_request="promise GA",
        source="t",
        run_mode=RunMode.DRY_RUN,
    )
    state["change"] = serialize(change)
    state["impact"] = serialize(ImpactEvidence(tags=tags))
    return state


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
