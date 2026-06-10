"""The LLM client's retry budget is explicit config; failures classify into a stable taxonomy."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import httpx
import openai
import pytest

from app.adapters.llm.azure_openai import AzureOpenAILLMProvider, _error_class
from app.observability import metrics
from app.ports.llm import LlmRequest


def test_client_is_constructed_with_the_configured_retry_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class _FakeAzure:
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)

    monkeypatch.setattr("app.adapters.llm.azure_openai.AzureOpenAI", _FakeAzure)
    AzureOpenAILLMProvider(
        endpoint="https://e", deployment="d", api_version="v", api_key="k", max_retries=5
    )
    assert captured["max_retries"] == 5


def _raising_provider(exc: Exception) -> AzureOpenAILLMProvider:
    def create(**_: Any) -> Any:
        raise exc

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    return AzureOpenAILLMProvider(
        endpoint="https://x", deployment="d", api_version="v", client=client
    )


def _rate_limit_error() -> openai.RateLimitError:
    request = httpx.Request("POST", "https://x")
    return openai.RateLimitError(
        "throttled", response=httpx.Response(429, request=request), body=None
    )


def _counter(name: str) -> int:
    counters = metrics.snapshot()["counters"]
    assert isinstance(counters, dict)
    return int(counters.get(name, 0))


def test_rate_limit_failures_count_and_still_propagate() -> None:
    provider = _raising_provider(_rate_limit_error())
    before = _counter("llm.errors.rate_limited")
    with pytest.raises(openai.RateLimitError):
        provider.generate(LlmRequest(prompt="p"))
    assert _counter("llm.errors.rate_limited") == before + 1


def test_error_taxonomy_orders_the_nested_sdk_types() -> None:
    request = httpx.Request("POST", "https://x")
    assert _error_class(_rate_limit_error()) == "rate_limited"
    assert _error_class(openai.APITimeoutError(request=request)) == "timeout"
    assert _error_class(openai.APIConnectionError(request=request)) == "connection"
    assert (
        _error_class(
            openai.InternalServerError(
                "boom", response=httpx.Response(503, request=request), body=None
            )
        )
        == "server"
    )
    assert (
        _error_class(
            openai.BadRequestError(
                "bad schema", response=httpx.Response(400, request=request), body=None
            )
        )
        == "invalid_request"
    )
    assert _error_class(RuntimeError("?")) == "unknown"
