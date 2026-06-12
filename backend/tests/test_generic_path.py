"""The generic path: agentic perception and planning for subjects with no registered scenario."""

from __future__ import annotations

from app.agent.gatherers import gather_nothing
from app.agent.nodes.execute import ExecuteNode
from app.agent.nodes.impact import ImpactNode
from app.agent.nodes.options import OptionsNode
from app.agent.planners import generic_planner
from app.agent.policy_rules.packs import default_packs
from app.agent.policy_rules.vocabulary import marks_unsafe_tags
from app.agent.state import CourtState, initial_state, serialize
from app.domain import (
    Change,
    ChangeStatus,
    ExecutionPlan,
    ImpactEvidence,
    PlanKind,
    RequestedAction,
    RunMode,
    Verdict,
    VerdictType,
)
from app.domain.impact import GroundedFact
from app.ports.knowledge import KnowledgePort
from tests.conftest import build_mock_registry

_UNSAFE = marks_unsafe_tags(default_packs())


def _change(subject: str | None = "channel-archival") -> Change:
    return Change(
        change_id="c1",
        raw_request="archive the old project channels",
        subject=subject,
        requested_actions=[
            RequestedAction(system="teams", capability_name="teams.post_message", params={})
        ],
    )


def _state(change: Change, tags: list[str]) -> CourtState:
    state = initial_state(
        thread_id="t1",
        change_id=change.change_id,
        raw_request=change.raw_request,
        source="test",
        run_mode=RunMode.DRY_RUN,
    )
    state["change"] = serialize(change)
    state["impact"] = serialize(ImpactEvidence(tags=tags))
    return state


def test_vocabulary_derives_the_known_unsafe_tags() -> None:
    assert _UNSAFE == {
        "schedule.target_date_conflict",
        "schedule.contractual_breach_risk",
        "security.review_after_due_date",
        "access.overbroad_scope",
    }


def test_generic_planner_passes_through_when_no_unsafe_tag_fired() -> None:
    plan = generic_planner(_UNSAFE)(_change(), ImpactEvidence(tags=["report.activity_collected"]))
    assert plan.kind is PlanKind.FEASIBLE
    assert [s.capability.name for s in plan.steps] == ["teams.post_message"]


def test_generic_planner_refuses_on_a_fired_unsafe_tag() -> None:
    plan = generic_planner(_UNSAFE)(
        _change(), ImpactEvidence(tags=["access.overbroad_scope", "x.other"])
    )
    assert plan.kind is PlanKind.SAFE_ALTERNATIVE
    assert plan.steps == []  # a pure refusal: no generic alternative is drafted offline
    assert "access.overbroad_scope" in plan.rationale


def test_options_node_routes_unknown_subjects_to_the_default_planner() -> None:
    node = OptionsNode({}, default_planner=generic_planner(_UNSAFE))
    result = node(_state(_change(), tags=["access.overbroad_scope"]))
    plan = ExecutionPlan.model_validate(result["options"])
    assert plan.kind is PlanKind.SAFE_ALTERNATIVE
    change = Change.model_validate(result["change"])
    assert change.unsafe is True  # the refusal marks the change, exactly as scenario planners do


def test_impact_node_routes_unknown_subjects_to_the_default_gatherer() -> None:
    calls: list[str] = []

    def spy_gatherer(change, registry, knowledge, errors):  # type: ignore[no-untyped-def]
        calls.append(change.subject or "")
        return gather_nothing(change, registry, knowledge, errors)

    class _NoKnowledge(KnowledgePort):
        def ground(self, query: str, *, top_k: int = 3) -> list[GroundedFact]:
            return []

    node = ImpactNode(build_mock_registry(), _NoKnowledge(), {}, default_gatherer=spy_gatherer)
    node(_state(_change(), tags=[]))
    assert calls == ["channel-archival"]


def test_empty_safe_alternative_executes_as_a_pure_refusal() -> None:
    # An accepted empty-steps alternative runs zero steps and completes — refusal without
    # execution is a legal terminal outcome of the generic path.
    state = _state(_change(), tags=[])
    state["options"] = serialize(ExecutionPlan(kind=PlanKind.SAFE_ALTERNATIVE, steps=[]))
    state["verdict"] = serialize(
        Verdict(verdict_id="v1", type=VerdictType.ACCEPT_ALTERNATIVE, idempotency_key="k1")
    )
    result = ExecuteNode(build_mock_registry())(state)
    assert result["results"] == []
    assert result["status"] == ChangeStatus.DONE.value
