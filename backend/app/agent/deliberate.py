"""Deliberation capture: each node's reasoning for its conclusion, honestly sourced.

A node hands the ``Deliberator`` a concise factual ``context`` (always available, built from the
node's structured outputs) and, when an agentic role has already reasoned, that ``reasoning`` prose.
The LLM-backed deliberator passes the role's reasoning through, or turns the context into reasoned
prose when there is none; the offline deliberator records the factual context, labeled as a stub.

Provenance is honest by construction: ``LlmDeliberator`` is wired exactly when the Prosecutor and
Defender are LLM-backed (the same ``llm_is_real`` switch), so reused role prose is genuinely
LLM-sourced. Nodes depend only on the ``Deliberator`` protocol (DIP); the concrete choice is made at
the composition root. The trace is append-only and never affects risk, quorum, or the verdict.
"""

from __future__ import annotations

import logging
from typing import Protocol

from app.agent.state import CourtState, bound_deliberations
from app.domain import SOURCE_LLM, SOURCE_OFFLINE_STUB, DeliberationEntry
from app.ports.llm import LLMProvider

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


class LlmDeliberator:
    """Surfaces genuine model reasoning: a role's prose, or an LLM explanation of the context."""

    def __init__(self, llm: LLMProvider) -> None:
        self._llm = llm

    def deliberate(
        self, *, node: str, role: str, context: str, reasoning: str = ""
    ) -> DeliberationEntry:
        text = reasoning.strip()
        if not text:
            try:
                text = self._llm.complete(
                    context, system=_SYSTEM_PROMPTS.get(node, _DEFAULT_SYSTEM)
                ).strip()
            except Exception as exc:  # noqa: BLE001 — reasoning is advisory; never fail a node
                logger.warning("deliberate.llm_fallback", extra={"node": node, "error": str(exc)})
                return DeliberationEntry(
                    node=node,
                    role=role,
                    rationale=context[:_MAX_RATIONALE_CHARS],
                    source=SOURCE_OFFLINE_STUB,
                )
        return DeliberationEntry(
            node=node, role=role, rationale=text[:_MAX_RATIONALE_CHARS], source=SOURCE_LLM
        )


def record(state: CourtState, entry: DeliberationEntry) -> list[dict[str, object]]:
    """Append ``entry`` to the (bounded) trace a node writes back, preserving prior entries."""
    return bound_deliberations([*state.get("deliberations", []), entry.model_dump(mode="json")])
