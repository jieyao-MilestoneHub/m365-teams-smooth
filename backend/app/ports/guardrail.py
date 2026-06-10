"""The guardrail port: screen untrusted input for prompt-injection / jailbreak before the model.

This is the input-shield seam. A heuristic implementation backs it credential-free during local
development; a managed shield (Azure AI Content Safety Prompt Shields) plugs in behind the same
interface with no change to the agentic nodes. Like the knowledge port, screening degrades
gracefully — it never raises — so a slow or unavailable shield costs the trial its screening, never
the trial itself.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from app.domain import ShieldVerdict


class GuardrailPort(ABC):
    """Classifies whether untrusted input is attempting to subvert the model's instructions."""

    @abstractmethod
    def screen_input(
        self, *, user_text: str, documents: Sequence[str] = ()
    ) -> ShieldVerdict:
        """Return a verdict on ``user_text`` (and any retrieved ``documents``).

        Implementations must not raise — on provider failure, return an unflagged verdict whose
        ``source`` marks the screening unavailable, so the caller can log it and proceed.
        """
