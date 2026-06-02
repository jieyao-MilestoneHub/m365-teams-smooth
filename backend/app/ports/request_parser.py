"""The request-parser port: turn a raw natural-language request into a structured Change.

Intake depends on this port, not on a concrete parser — a deterministic parser is the reliable
default, and an LLM-backed parser plugs in behind the same interface. Implementations must not
raise: when unsure they fall back (the LLM-backed parser delegates to the deterministic one), so
intake always receives a Change and the hallucination guard does the final validation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain import Change


class RequestParser(ABC):
    """Parses a natural-language request into a structured Change (subject + requested actions)."""

    @abstractmethod
    def parse(self, raw: str, *, change_id: str) -> Change:
        """Produce a structured Change for ``raw``. Never raises; falls back when unsure."""
