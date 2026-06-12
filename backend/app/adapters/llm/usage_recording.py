"""Usage-recording wrapper: feeds each call's token telemetry to the per-node accumulator.

Wraps the one real provider at the composition root, inside any model-tier wrapper, so a
per-request ``model`` set by the tier (or a call site) attributes the usage to the deployment that
actually served it. Only successful calls are recorded — a raised call has no usage object to
read, and the provider's ``llm.call_failed`` log already covers it.
"""

from __future__ import annotations

from app.observability import llm_usage
from app.ports.llm import LLMProvider, LlmRequest, LlmResult


class UsageRecordingLLMProvider(LLMProvider):
    """Delegates to an inner provider and records each result's usage for the current node."""

    def __init__(self, inner: LLMProvider, *, default_model: str) -> None:
        self._inner = inner
        self._default_model = default_model

    def complete(self, prompt: str, *, system: str | None = None) -> str:
        return self.generate(LlmRequest(prompt=prompt, cacheable_prefix=system)).text

    def generate(self, request: LlmRequest) -> LlmResult:
        result = self._inner.generate(request)
        llm_usage.record(
            request.model or self._default_model,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            cached_tokens=result.cached_prefix_tokens,
        )
        return result
