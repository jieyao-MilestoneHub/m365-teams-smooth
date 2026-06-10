"""The Azure adapter engages native structured output and rejects unusable responses."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.adapters.llm.azure_openai import AzureOpenAILLMProvider
from app.domain.errors import LlmOutputError
from app.ports.llm import LlmRequest


class _CapturingClient:
    """Records the kwargs of chat.completions.create and returns a canned response."""

    def __init__(self, response: Any) -> None:
        self.kwargs: dict[str, Any] = {}
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))
        self._response = response

    def _create(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        return self._response


def _response(content: str = "{}", finish_reason: str = "stop", refusal: str | None = None) -> Any:
    message = SimpleNamespace(content=content, refusal=refusal)
    return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason=finish_reason)])


def _provider(client: _CapturingClient, **kwargs: Any) -> AzureOpenAILLMProvider:
    return AzureOpenAILLMProvider(
        endpoint="https://x", deployment="gpt-4o", api_version="2024-10-21",
        client=client, **kwargs,
    )


def test_json_schema_becomes_strict_response_format() -> None:
    client = _CapturingClient(_response('{"a": 1}'))
    schema = {"type": "object", "properties": {"a": {"type": "integer"}},
              "required": ["a"], "additionalProperties": False}
    result = _provider(client).generate(
        LlmRequest(prompt="p", cacheable_prefix="sys", json_schema=schema, schema_name="thing")
    )
    assert result.text == '{"a": 1}'
    response_format = client.kwargs["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["name"] == "thing"
    assert response_format["json_schema"]["strict"] is True
    assert response_format["json_schema"]["schema"] == schema
    assert client.kwargs["messages"][0] == {"role": "system", "content": "sys"}


def test_free_text_requests_send_no_response_format() -> None:
    client = _CapturingClient(_response("prose"))
    _provider(client).generate(LlmRequest(prompt="p"))
    assert "response_format" not in client.kwargs


def test_per_call_max_tokens_overrides_the_provider_default() -> None:
    client = _CapturingClient(_response())
    _provider(client, max_tokens=1024).generate(LlmRequest(prompt="p", max_tokens=256))
    assert client.kwargs["max_tokens"] == 256
    _provider(client, max_tokens=1024).generate(LlmRequest(prompt="p"))
    assert client.kwargs["max_tokens"] == 1024


def test_truncated_structured_response_raises() -> None:
    client = _CapturingClient(_response('{"a":', finish_reason="length"))
    with pytest.raises(LlmOutputError, match="truncated"):
        _provider(client).generate(LlmRequest(prompt="p", json_schema={"type": "object"}))


def test_refused_structured_response_raises() -> None:
    client = _CapturingClient(_response("", refusal="cannot comply"))
    with pytest.raises(LlmOutputError, match="refused"):
        _provider(client).generate(LlmRequest(prompt="p", json_schema={"type": "object"}))


def test_truncated_free_text_is_tolerated() -> None:
    # Truncated prose (e.g. a deliberation note) is still useful; only schema output must be whole.
    client = _CapturingClient(_response("half a thought", finish_reason="length"))
    assert _provider(client).generate(LlmRequest(prompt="p")).text == "half a thought"


def test_complete_round_trips_through_generate() -> None:
    client = _CapturingClient(_response("hi"))
    assert _provider(client).complete("hello", system="be terse") == "hi"
    assert client.kwargs["messages"] == [
        {"role": "system", "content": "be terse"},
        {"role": "user", "content": "hello"},
    ]
