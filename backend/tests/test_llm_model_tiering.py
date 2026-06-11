"""Per-call model tiering: a request's model override reaches the provider, and the tier
wrapper defaults it for a call site without touching explicit overrides."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from app.adapters.llm.azure_openai import AzureOpenAILLMProvider
from app.adapters.llm.tiered import ModelTierLLMProvider
from app.ports.llm import LLMProvider, LlmRequest, LlmResult

# --- adapter: the override selects the deployment ---------------------------------------------


def _client() -> Any:
    holder = SimpleNamespace(kwargs={})

    def create(**kwargs: Any) -> Any:
        holder.kwargs = kwargs
        message = SimpleNamespace(content="ok", refusal=None)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=message, finish_reason="stop")], usage=None
        )

    holder.chat = SimpleNamespace(completions=SimpleNamespace(create=create))
    return holder


def _provider(client: Any) -> AzureOpenAILLMProvider:
    return AzureOpenAILLMProvider(
        endpoint="https://x", deployment="gpt-4o", api_version="2024-10-21", client=client
    )


def test_request_model_overrides_the_default_deployment() -> None:
    client = _client()
    _provider(client).generate(LlmRequest(prompt="p", model="gpt-4o-mini"))
    assert client.kwargs["model"] == "gpt-4o-mini"


def test_without_an_override_the_default_deployment_is_used() -> None:
    client = _client()
    _provider(client).generate(LlmRequest(prompt="p"))
    assert client.kwargs["model"] == "gpt-4o"


# --- tier wrapper: defaults the model per call site --------------------------------------------


class _RecordingLLM(LLMProvider):
    def __init__(self) -> None:
        self.requests: list[LlmRequest] = []

    def complete(self, prompt: str, *, system: str | None = None) -> str:
        return "ok"

    def generate(self, request: LlmRequest) -> LlmResult:
        self.requests.append(request)
        return LlmResult(text="ok")


def test_tier_wrapper_defaults_a_missing_model() -> None:
    inner = _RecordingLLM()
    ModelTierLLMProvider(inner, model="gpt-4o-mini").generate(LlmRequest(prompt="p"))
    assert inner.requests[0].model == "gpt-4o-mini"


def test_tier_wrapper_preserves_an_explicit_model() -> None:
    inner = _RecordingLLM()
    ModelTierLLMProvider(inner, model="gpt-4o-mini").generate(
        LlmRequest(prompt="p", model="gpt-4o")
    )
    assert inner.requests[0].model == "gpt-4o"


def test_tier_wrapper_preserves_the_rest_of_the_request() -> None:
    inner = _RecordingLLM()
    ModelTierLLMProvider(inner, model="gpt-4o-mini").generate(
        LlmRequest(prompt="p", cacheable_prefix="catalog", json_schema={}, max_tokens=64)
    )
    request = inner.requests[0]
    assert (request.prompt, request.cacheable_prefix, request.max_tokens) == ("p", "catalog", 64)
    assert request.json_schema == {}


def test_tier_wrapper_routes_complete_through_the_tier() -> None:
    inner = _RecordingLLM()
    assert ModelTierLLMProvider(inner, model="gpt-4o-mini").complete("p", system="s") == "ok"
    request = inner.requests[0]
    assert (request.model, request.prompt, request.cacheable_prefix) == ("gpt-4o-mini", "p", "s")
