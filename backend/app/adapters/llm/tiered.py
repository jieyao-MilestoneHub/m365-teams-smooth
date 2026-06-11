"""Model-tier wrapper: defaults a call site's requests onto a specific deployment.

The composition root maps call sites to deployment tiers by wrapping the one real provider —
lightweight work (the request parser, the deliberation trace) on a cheaper/faster deployment while
the reasoning-heavy roles (Prosecutor, Defender) keep the provider default. The wrapper only fills
in a missing ``model``: an explicit per-request override always wins, and providers that ignore the
field (the offline fake) behave exactly as before.
"""

from __future__ import annotations

from dataclasses import replace

from app.ports.llm import LLMProvider, LlmRequest, LlmResult


class ModelTierLLMProvider(LLMProvider):
    """Delegates to an inner provider with requests defaulted to a fixed model tier."""

    def __init__(self, inner: LLMProvider, *, model: str) -> None:
        self._inner = inner
        self._model = model

    def complete(self, prompt: str, *, system: str | None = None) -> str:
        return self.generate(LlmRequest(prompt=prompt, cacheable_prefix=system)).text

    def generate(self, request: LlmRequest) -> LlmResult:
        if request.model is None:
            request = replace(request, model=self._model)
        return self._inner.generate(request)
