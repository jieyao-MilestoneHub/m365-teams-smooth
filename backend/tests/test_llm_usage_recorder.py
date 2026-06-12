"""Per-node LLM usage accumulation: the thread-local slot and the recording provider wrapper."""

from __future__ import annotations

import threading

from app.adapters.llm.usage_recording import UsageRecordingLLMProvider
from app.observability import llm_usage
from app.ports.llm import LLMProvider, LlmRequest, LlmResult


class _StubProvider(LLMProvider):
    def __init__(self) -> None:
        self.requests: list[LlmRequest] = []

    def complete(self, prompt: str, *, system: str | None = None) -> str:
        return self.generate(LlmRequest(prompt=prompt, cacheable_prefix=system)).text

    def generate(self, request: LlmRequest) -> LlmResult:
        self.requests.append(request)
        return LlmResult(text="ok", input_tokens=100, output_tokens=20, cached_prefix_tokens=64)


def test_record_and_drain_round_trip() -> None:
    llm_usage.reset()
    llm_usage.record("gpt-a", input_tokens=10, output_tokens=2, cached_tokens=0)
    llm_usage.record("gpt-b", input_tokens=5, output_tokens=1, cached_tokens=3)

    assert llm_usage.drain() == {
        "calls": 2,
        "input_tokens": 15,
        "output_tokens": 3,
        "cached_tokens": 3,
        "deployments": ["gpt-a", "gpt-b"],
    }
    assert llm_usage.drain() is None  # drained slot is empty


def test_drain_returns_none_on_empty_slot() -> None:
    llm_usage.reset()
    assert llm_usage.drain() is None


def test_threads_have_isolated_slots() -> None:
    llm_usage.reset()
    seen: dict[str, dict[str, object] | None] = {}

    def worker(name: str, tokens: int) -> None:
        llm_usage.record("gpt", input_tokens=tokens, output_tokens=0, cached_tokens=0)
        seen[name] = llm_usage.drain()

    threads = [
        threading.Thread(target=worker, args=("a", 7)),
        threading.Thread(target=worker, args=("b", 11)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert seen["a"] is not None and seen["a"]["input_tokens"] == 7
    assert seen["b"] is not None and seen["b"]["input_tokens"] == 11
    assert llm_usage.drain() is None  # the main thread's slot saw nothing


def test_recording_provider_attributes_to_request_model_or_default() -> None:
    llm_usage.reset()
    provider = UsageRecordingLLMProvider(_StubProvider(), default_model="gpt-default")

    provider.generate(LlmRequest(prompt="p"))
    provider.generate(LlmRequest(prompt="p", model="gpt-fast"))

    usage = llm_usage.drain()
    assert usage is not None
    assert usage["calls"] == 2
    assert usage["input_tokens"] == 200
    assert usage["output_tokens"] == 40
    assert usage["cached_tokens"] == 128
    assert usage["deployments"] == ["gpt-default", "gpt-fast"]


def test_recording_provider_routes_complete_through_generate() -> None:
    llm_usage.reset()
    stub = _StubProvider()
    provider = UsageRecordingLLMProvider(stub, default_model="gpt-default")

    assert provider.complete("hello", system="sys") == "ok"
    assert stub.requests[0].cacheable_prefix == "sys"

    usage = llm_usage.drain()
    assert usage is not None and usage["calls"] == 1
