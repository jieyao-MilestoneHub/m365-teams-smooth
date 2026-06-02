"""The LLM provider port: free-text generation for the court (rationale, drafts).

Structured parsing (intake → actions) is deterministic and constrained to registered capabilities,
so it does not depend on this port. Keeping the LLM a text generator leaves the trials reproducible
while still offering a seam for a real provider.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """Generates free text from a prompt."""

    @abstractmethod
    def complete(self, prompt: str, *, system: str | None = None) -> str:
        """Return a completion for ``prompt`` (optionally steered by a ``system`` instruction)."""
