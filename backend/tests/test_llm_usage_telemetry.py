"""Every real LLM call surfaces token usage and the provider request id."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from app.adapters.llm.azure_openai import AzureOpenAILLMProvider
from app.observability import metrics
from app.ports.llm import LlmRequest, LlmResult


def _response(*, prompt_tokens: int, completion_tokens: int, cached_tokens: int) -> Any:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="ok", refusal=None), finish_reason="stop"
            )
        ],
        usage=SimpleNamespace(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            prompt_tokens_details=SimpleNamespace(cached_tokens=cached_tokens),
        ),
        _request_id="req_abc123",
    )


def _provider(response: Any) -> AzureOpenAILLMProvider:
    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **_: response))
    )
    return AzureOpenAILLMProvider(
        endpoint="https://x", deployment="d", api_version="v", client=client
    )


def _counter(name: str) -> int:
    counters = metrics.snapshot()["counters"]
    assert isinstance(counters, dict)
    return int(counters.get(name, 0))


def test_usage_and_request_id_surface_on_the_result() -> None:
    provider = _provider(_response(prompt_tokens=2048, completion_tokens=120, cached_tokens=1536))
    result = provider.generate(LlmRequest(prompt="p", cacheable_prefix="catalog"))
    assert result.input_tokens == 2048
    assert result.output_tokens == 120
    assert result.cached_prefix_tokens == 1536
    assert result.request_id == "req_abc123"


def test_token_counters_accumulate_per_call() -> None:
    provider = _provider(_response(prompt_tokens=100, completion_tokens=10, cached_tokens=64))
    before = {
        name: _counter(name)
        for name in ("llm.calls", "llm.tokens.input", "llm.tokens.output", "llm.tokens.cached")
    }
    provider.generate(LlmRequest(prompt="p"))
    provider.generate(LlmRequest(prompt="q"))
    assert _counter("llm.calls") == before["llm.calls"] + 2
    assert _counter("llm.tokens.input") == before["llm.tokens.input"] + 200
    assert _counter("llm.tokens.output") == before["llm.tokens.output"] + 20
    assert _counter("llm.tokens.cached") == before["llm.tokens.cached"] + 128


def test_missing_usage_defaults_stay_empty() -> None:
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="ok", refusal=None), finish_reason="stop"
            )
        ]
    )
    result = _provider(response).generate(LlmRequest(prompt="p"))
    assert (result.input_tokens, result.output_tokens, result.cached_prefix_tokens) == (0, 0, 0)
    assert result.request_id is None


def test_port_defaults_keep_offline_stubs_unchanged() -> None:
    result = LlmResult(text="offline")
    assert (result.input_tokens, result.output_tokens, result.request_id) == (0, 0, None)
