"""Deliberation capture: each node's reasoning for the conclusion it reached.

A node hands the ``Deliberator`` a concise factual ``context`` (built from the node's structured
outputs) and, when an agentic role has already reasoned, that ``reasoning`` prose. The LLM-backed
deliberator passes the role's reasoning through, or turns the context into reasoned prose when there
is none; the offline deliberator records the factual context, labeled as a stub. Each entry carries
its source, so the surfaces can show whether a model reasoned or the run was offline.

The trace is append-only and never affects risk, quorum, or the verdict — it explains the decision,
it does not make it.
"""

from __future__ import annotations

import logging
from typing import Protocol

from app.agent.state import CourtState, bound_deliberations
from app.domain import SOURCE_LLM, SOURCE_OFFLINE_STUB, DeliberationEntry
from app.ports.llm import LLMProvider, LlmRequest

logger = logging.getLogger(__name__)

_MAX_RATIONALE_CHARS = 600

_DEFAULT_SYSTEM = (
    "You preside over a change-governance court. In 2-3 sentences, explain the reasoning behind "
    "this step's conclusion. Be specific and concrete; do not restate the facts verbatim."
)
_SYSTEM_PROMPTS = {
    "intake": (
        "You are the court Clerk. In 2-3 sentences, explain how the request was understood and why "
        "any requested action was kept or rejected against the registered capabilities."
    ),
    "policy": (
        "You preside over the court. In 2-3 sentences, explain why this risk level and approval "
        "requirement are warranted given the factors that fired, and who must sign off."
    ),
    "verify": (
        "You are the court Clerk reviewing execution. In 2-3 sentences, explain whether the writes "
        "that were applied match the reviewed plan, and call out any mismatch."
    ),
}


class Deliberator(Protocol):
    """Produces one node's reasoning entry from a factual context (and optional role prose)."""

    def deliberate(
        self, *, node: str, role: str, context: str, reasoning: str = ""
    ) -> DeliberationEntry: ...


class OfflineDeliberator:
    """Records the node's factual context as the rationale, honestly labeled as a stub."""

    def deliberate(
        self, *, node: str, role: str, context: str, reasoning: str = ""
    ) -> DeliberationEntry:
        return DeliberationEntry(
            node=node,
            role=role,
            rationale=context[:_MAX_RATIONALE_CHARS],
            source=SOURCE_OFFLINE_STUB,
        )


# The deliberator emits 2-3 sentences; cap it well below the uniform 1024 to bound spend.
_DELIBERATION_MAX_TOKENS = 256


class LlmDeliberator:
    """Surfaces genuine model reasoning: a role's prose, or an LLM explanation of the context.

    The deliberation trace is purely explanatory — it never affects risk, quorum, or the verdict —
    yet it is the highest-volume LLM spend (up to one call per node). With ``dedicated_calls`` off
    (the default "reuse" cadence), it makes a model call only when an upstream role already produced
    prose; absent prose it records the factual context as an honestly-labeled stub, so a trial pays
    ~0 dedicated deliberation calls. ``dedicated_calls`` on restores a model call for every node.
    """

    def __init__(self, llm: LLMProvider, *, dedicated_calls: bool = False) -> None:
        self._llm = llm
        self._dedicated_calls = dedicated_calls

    def deliberate(
        self, *, node: str, role: str, context: str, reasoning: str = ""
    ) -> DeliberationEntry:
        text = reasoning.strip()
        if text:
            return DeliberationEntry(
                node=node, role=role, rationale=text[:_MAX_RATIONALE_CHARS], source=SOURCE_LLM
            )
        if not self._dedicated_calls:
            # Reuse cadence: no upstream prose → record the factual context, no dedicated call.
            return DeliberationEntry(
                node=node, role=role, rationale=context[:_MAX_RATIONALE_CHARS],
                source=SOURCE_OFFLINE_STUB,
            )
        try:
            result = self._llm.generate(
                LlmRequest(
                    prompt=context,
                    cacheable_prefix=_SYSTEM_PROMPTS.get(node, _DEFAULT_SYSTEM),
                    max_tokens=_DELIBERATION_MAX_TOKENS,
                )
            )
        except Exception as exc:  # noqa: BLE001 — reasoning is advisory; never fail a node
            logger.warning("deliberate.llm_fallback", extra={"node": node, "error": str(exc)})
            return DeliberationEntry(
                node=node, role=role, rationale=context[:_MAX_RATIONALE_CHARS],
                source=SOURCE_OFFLINE_STUB,
            )
        return DeliberationEntry(
            node=node, role=role, rationale=result.text.strip()[:_MAX_RATIONALE_CHARS],
            source=SOURCE_LLM,
        )


def record(state: CourtState, entry: DeliberationEntry) -> list[dict[str, object]]:
    """Append ``entry`` to the (bounded) trace a node writes back, preserving prior entries."""
    return bound_deliberations([*state.get("deliberations", []), entry.model_dump(mode="json")])
