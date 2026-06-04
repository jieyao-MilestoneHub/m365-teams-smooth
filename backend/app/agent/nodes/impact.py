"""Impact node (Prosecutor): gather second-order consequences as tagged, grounded evidence.

The node runs the gatherer registered for the change's subject (the per-trial read-capability logic
lands in #84) and grounds the request through the knowledge port, so evidence carries citations from
the Microsoft IQ layer. It emits an ``ImpactEvidence`` whose tags are the hooks policy/quorum match.
"""

from __future__ import annotations

from typing import Protocol

from app.agent.state import CourtState, bound_errors, serialize
from app.domain import Change, ChangeStatus, EvidenceItem, ImpactEvidence
from app.ports.knowledge import KnowledgePort
from app.ports.registry import IntegrationRegistry


class Gatherer(Protocol):
    """Produces evidence (items + tags) for one change subject via read capabilities.

    A failed read appends a message to ``errors`` and is skipped, so evidence degrades
    gracefully rather than aborting the node.
    """

    def __call__(
        self,
        change: Change,
        registry: IntegrationRegistry,
        knowledge: KnowledgePort,
        errors: list[str],
    ) -> ImpactEvidence: ...


def _merge(into: ImpactEvidence, other: ImpactEvidence) -> None:
    into.items.extend(other.items)
    for tag in other.tags:
        if tag not in into.tags:
            into.tags.append(tag)


class ImpactNode:
    """Aggregates evidence from the subject's gatherer and grounds it through the knowledge port."""

    def __init__(
        self,
        registry: IntegrationRegistry,
        knowledge: KnowledgePort,
        gatherers: dict[str, Gatherer],
    ) -> None:
        self._registry = registry
        self._knowledge = knowledge
        self._gatherers = gatherers

    def __call__(self, state: CourtState) -> CourtState:
        change = Change.model_validate(state["change"])
        evidence = ImpactEvidence()
        errors = list(state.get("errors", []))

        gatherer = self._gatherers.get(change.subject or "")
        if gatherer is not None:
            _merge(evidence, gatherer(change, self._registry, self._knowledge, errors))

        # Grounding degrades gracefully (like a failed gatherer read): a slow or down knowledge
        # service costs the trial its citations, never the trial itself.
        try:
            facts = self._knowledge.ground(change.raw_request)
        except Exception as exc:  # noqa: BLE001 — any provider failure becomes evidence-level
            facts = []
            errors.append(f"knowledge grounding unavailable: {exc}")
        if facts:
            evidence.items.append(
                EvidenceItem(
                    system="knowledge",
                    kind="grounding",
                    summary="grounded governance facts",
                    grounded=facts,
                )
            )

        return {
            "impact": serialize(evidence),
            "status": ChangeStatus.EVALUATING.value,
            "errors": bound_errors(errors),
        }
