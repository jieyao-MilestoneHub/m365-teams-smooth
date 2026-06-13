"""The guardrail port: screen untrusted input for prompt-injection / jailbreak before the model.

This is the input-shield seam. A heuristic implementation backs it credential-free during local
development; a managed shield (Azure AI Content Safety Prompt Shields) plugs in behind the same
interface with no change to the agentic nodes. The offline heuristic never raises. A *configured
real* shield that cannot screen (transport, auth, timeout) **raises** instead of returning an
unflagged verdict — unscreened input is never assumed safe (fail loud, per the quality policy).
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

        The offline heuristic never raises. A configured real shield that cannot screen raises a
        ``GuardrailError`` rather than returning an unflagged verdict — the caller must not proceed
        as if unscreened input were safe.
        """
