"""The knowledge port: permission-aware, cited grounding for impact evidence.

This is the Microsoft IQ seam. An offline fake backs it during local development; a managed
knowledge layer (Azure AI Foundry / Foundry IQ over Azure AI Search) plugs in behind the same
interface with no change to the impact node or the graph.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain import GroundedFact


class KnowledgePort(ABC):
    """Retrieves grounded, cited facts relevant to a query."""

    @abstractmethod
    def ground(self, query: str, *, top_k: int = 3) -> list[GroundedFact]:
        """Return up to ``top_k`` cited facts relevant to ``query`` (most relevant first)."""
