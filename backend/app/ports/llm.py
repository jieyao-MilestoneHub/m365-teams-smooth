"""The LLM provider port: generation for the court's LLM-backed roles and deliberation.

Every LLM call site keeps a deterministic counterpart (parser, gatherer, planner, deliberator), so
trials stay reproducible whether this port is the offline fake or a real provider.

``generate`` carries provider-agnostic caching / structured-output / per-call intent without leaking
SDK types: a stable ``cacheable_prefix`` (so providers can cache the static catalog), a volatile
``system_suffix``, an optional JSON schema (a plain dict — no SDK types), and a per-call token cap.
The result carries per-call usage telemetry alongside the text. ``generate`` is a concrete method
whose default delegates to ``complete``, so the offline fake, test stubs, and the deliberator keep
working unchanged; adapters override it to exploit the extra intent.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class LlmRequest:
    """A generation request that separates cacheable, volatile, and structured intent."""

    prompt: str
    cacheable_prefix: str | None = None  # stable across calls/trials → a cacheable prefix
    system_suffix: str | None = None  # volatile system text, after the cacheable prefix
    json_schema: dict[str, object] | None = None  # plain JSON Schema; no SDK types
    schema_name: str = "response"
    max_tokens: int | None = None  # per-call override of the provider default


@dataclass(frozen=True)
class LlmResult:
    """A generation result plus per-call observability (token usage, provider request id).

    The telemetry fields default to empty so offline fakes and test stubs satisfy the port
    without ever touching them; real adapters fill them from the provider's usage accounting.
    """

    text: str
    cached_prefix_tokens: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    request_id: str | None = None


class LLMProvider(ABC):
    """Generates free text from a prompt."""

    @abstractmethod
    def complete(self, prompt: str, *, system: str | None = None) -> str:
        """Return a completion for ``prompt`` (optionally steered by a ``system`` instruction)."""

    def generate(self, request: LlmRequest) -> LlmResult:
        """Generate from a structured request.

        The default joins the cacheable prefix and volatile suffix into one system string and
        round-trips through ``complete`` — so any provider that only implements ``complete`` (the
        offline fake, test stubs) works without change. Adapters override this to engage caching,
        structured output, and per-call token control.
        """
        system = "\n".join(p for p in (request.cacheable_prefix, request.system_suffix) if p)
        return LlmResult(text=self.complete(request.prompt, system=system or None))
