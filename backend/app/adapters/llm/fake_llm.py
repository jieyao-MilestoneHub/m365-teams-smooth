"""Offline, deterministic LLM provider — the default for local and fully-mocked runs.

It performs no network I/O and returns reproducible text, so trials are stable. Nodes that need
precise wording (e.g. an email draft) template it themselves rather than relying on free generation.
"""

from __future__ import annotations

from app.ports.llm import LLMProvider


class FakeLLMProvider(LLMProvider):
    """Returns a deterministic, single-line echo of the prompt."""

    def __init__(self, *, prefix: str = "[offline-llm]") -> None:
        self._prefix = prefix

    def complete(self, prompt: str, *, system: str | None = None) -> str:
        lines = [line.strip() for line in prompt.strip().splitlines() if line.strip()]
        summary = lines[0] if lines else ""
        return f"{self._prefix} {summary}".strip()
