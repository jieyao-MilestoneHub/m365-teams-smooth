"""The impact node runs the subject's gatherer and grounds evidence with cited facts."""

from __future__ import annotations

from app.adapters.integrations.registry import ConfigIntegrationRegistry
from app.adapters.knowledge.local_corpus import LocalCorpusKnowledgeProvider
from app.agent.nodes.impact import ImpactNode
from app.agent.policy_rules.packs import default_packs
from app.agent.policy_rules.vocabulary import grounding_queries
from app.agent.state import CourtState, initial_state, serialize
from app.domain import (
    Change,
    EvidenceItem,
    GroundedFact,
    ImpactEvidence,
    RunMode,
)
from app.ports.knowledge import KnowledgePort
from app.ports.registry import IntegrationRegistry

_GROUNDING = grounding_queries(default_packs())


class _SpyKnowledge(KnowledgePort):
    """Records the exact query string the impact node grounds with."""

    def __init__(self) -> None:
        self.queries: list[str] = []

    def ground(self, query: str, *, top_k: int = 3) -> list[GroundedFact]:
        self.queries.append(query)
        return []


def _launch_gatherer(
    change: Change,
    registry: IntegrationRegistry,
    knowledge: KnowledgePort,
    errors: list[str],
) -> ImpactEvidence:
    return ImpactEvidence(
        items=[EvidenceItem(system="github", kind="milestone", summary="milestone moves")],
        tags=["schedule.milestone_move"],
    )


def _failing_gatherer(
    change: Change,
    registry: IntegrationRegistry,
    knowledge: KnowledgePort,
    errors: list[str],
) -> ImpactEvidence:
    errors.append("impact read failed on github.read_milestone: upstream unavailable")
    return ImpactEvidence()


def _state_with_change(change: Change) -> CourtState:
    state = initial_state(
        thread_id="t1",
        change_id=change.change_id,
        raw_request=change.raw_request,
        source="test",
        run_mode=RunMode.DRY_RUN,
    )
    state["change"] = serialize(change)
    return state


def test_impact_runs_subject_gatherer_and_grounds(
    mock_registry: ConfigIntegrationRegistry, knowledge: LocalCorpusKnowledgeProvider
) -> None:
    node = ImpactNode(
        mock_registry, knowledge, {"launch": _launch_gatherer}, grounding=_GROUNDING
    )
    change = Change(change_id="c1", raw_request="slip the launch milestone", subject="launch")

    result = node(_state_with_change(change))
    evidence = ImpactEvidence.model_validate(result["impact"])

    assert "schedule.milestone_move" in evidence.tags
    grounding = [i for i in evidence.items if i.kind == "grounding"]
    assert grounding and grounding[0].grounded  # cited facts attached


def test_impact_without_gatherer_still_grounds(
    mock_registry: ConfigIntegrationRegistry, knowledge: LocalCorpusKnowledgeProvider
) -> None:
    node = ImpactNode(mock_registry, knowledge, {}, grounding=_GROUNDING)
    change = Change(change_id="c1", raw_request="promise SSO is GA", subject="sso-ga")
    result = node(_state_with_change(change))
    evidence = ImpactEvidence.model_validate(result["impact"])
    assert any(i.kind == "grounding" for i in evidence.items)


def test_impact_surfaces_gatherer_read_errors_in_state(
    mock_registry: ConfigIntegrationRegistry, knowledge: LocalCorpusKnowledgeProvider
) -> None:
    node = ImpactNode(mock_registry, knowledge, {"launch": _failing_gatherer})
    change = Change(change_id="c1", raw_request="slip the launch", subject="launch")
    result = node(_state_with_change(change))
    assert result["errors"] == [
        "impact read failed on github.read_milestone: upstream unavailable"
    ]


def test_impact_grounds_the_subject_phrase_not_the_raw_request(
    mock_registry: ConfigIntegrationRegistry,
) -> None:
    spy = _SpyKnowledge()
    node = ImpactNode(mock_registry, spy, {}, grounding=_GROUNDING)
    change = Change(
        change_id="c1", raw_request="move the rehearsal to 2026-06-16", subject="launch"
    )
    node(_state_with_change(change))
    assert spy.queries == [_GROUNDING["launch"]]


def test_impact_grounds_the_raw_request_when_unclassified(
    mock_registry: ConfigIntegrationRegistry,
) -> None:
    spy = _SpyKnowledge()
    node = ImpactNode(mock_registry, spy, {})
    change = Change(
        change_id="c1", raw_request="something the parser did not classify", subject=None
    )
    node(_state_with_change(change))
    assert spy.queries == ["something the parser did not classify"]


def test_impact_grounds_the_raw_request_for_an_unmapped_subject(
    mock_registry: ConfigIntegrationRegistry,
) -> None:
    # A novel subject with no pack-supplied phrase grounds on the raw request — same degradation
    # as an unclassified change, so generic-path grounding never goes dark.
    spy = _SpyKnowledge()
    node = ImpactNode(mock_registry, spy, {}, grounding=_GROUNDING)
    change = Change(
        change_id="c1", raw_request="archive the old channels", subject="channel-archival"
    )
    node(_state_with_change(change))
    assert spy.queries == ["archive the old channels"]
