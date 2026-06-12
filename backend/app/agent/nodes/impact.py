"""Impact node (Prosecutor): gather second-order consequences as tagged, grounded evidence.

The node runs the gatherer registered for the change's subject and grounds the request through the
knowledge port, so evidence carries citations from the Microsoft IQ layer. It emits an
``ImpactEvidence`` whose tags are the hooks policy/quorum match.
"""

from __future__ import annotations

from typing import Protocol

from app.agent.deliberate import Deliberator, OfflineDeliberator, record
from app.agent.state import CourtState, bound_errors, bound_evidence, serialize
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
        deliberator: Deliberator | None = None,
        *,
        default_gatherer: Gatherer | None = None,
        grounding: dict[str, str] | None = None,
    ) -> None:
        self._registry = registry
        self._knowledge = knowledge
        self._gatherers = gatherers
        self._deliberator = deliberator or OfflineDeliberator()
        self._default_gatherer = default_gatherer
        self._grounding = dict(grounding or {})

    def __call__(self, state: CourtState) -> CourtState:
        change = Change.model_validate(state["change"])
        evidence = ImpactEvidence()
        errors = list(state.get("errors", []))

        gatherer = self._gatherers.get(change.subject or "") or self._default_gatherer
        if gatherer is not None:
            _merge(evidence, gatherer(change, self._registry, self._knowledge, errors))

        # Ground on the subject's targeted phrase (a bare request ranks poorly against the noisy
        # corpus); fall back to the raw request only when the change is unclassified. Grounding
        # degrades gracefully (like a failed gatherer read): a slow or down knowledge service costs
        # the trial its citations, never the trial itself.
        try:
            query = (
                self._grounding.get(change.subject, change.raw_request)
                if change.subject
                else change.raw_request
            )
            facts = self._knowledge.ground(query)
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

        # Keep the checkpointed state (and the Defender's prompt) small: bound the evidence, keeping
        # every high-severity finding plus the most-recent remainder.
        evidence.items = bound_evidence(evidence.items)

        # The Prosecutor (when LLM-backed) already reasoned in its assessment item; reuse it as the
        # impact reasoning. Offline, the deliberator records the factual evidence summary instead.
        assessment = next(
            (
                i.summary
                for i in evidence.items
                if i.system == "prosecutor" and i.kind == "assessment"
            ),
            "",
        )
        high = [i.summary for i in evidence.items if i.severity == "high"]
        context = (
            f"Gathered {len(evidence.items)} evidence item(s); tags: "
            f"{', '.join(evidence.tags) or 'none'}. "
            f"{'Decisive: ' + '; '.join(high) if high else 'No high-severity findings.'}"
        )
        entry = self._deliberator.deliberate(
            node="impact", role="prosecutor", context=context, reasoning=assessment
        )

        return {
            "impact": serialize(evidence),
            "status": ChangeStatus.EVALUATING.value,
            "errors": bound_errors(errors),
            "deliberations": record(state, entry),
        }
