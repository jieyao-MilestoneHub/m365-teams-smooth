"""The LLMProvider.generate default joins prefix+suffix and round-trips through complete()."""

from __future__ import annotations

from app.ports.llm import LLMProvider, LlmRequest, LlmResult


class _RecordingLLM(LLMProvider):
    """Records the (prompt, system) it was asked to complete; echoes a fixed reply."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []

    def complete(self, prompt: str, *, system: str | None = None) -> str:
        self.calls.append((prompt, system))
        return "ok"


def test_generate_joins_prefix_and_suffix() -> None:
    llm = _RecordingLLM()
    result = llm.generate(
        LlmRequest(prompt="do it", cacheable_prefix="CATALOG", system_suffix="be terse")
    )
    assert isinstance(result, LlmResult)
    assert result.text == "ok"
    assert result.cached_prefix_tokens == 0
    prompt, system = llm.calls[0]
    assert prompt == "do it"
    assert system == "CATALOG\nbe terse"


def test_generate_with_no_system_passes_none() -> None:
    llm = _RecordingLLM()
    llm.generate(LlmRequest(prompt="hi"))
    assert llm.calls[0] == ("hi", None)


def test_generate_with_only_prefix() -> None:
    llm = _RecordingLLM()
    llm.generate(LlmRequest(prompt="hi", cacheable_prefix="CATALOG"))
    assert llm.calls[0][1] == "CATALOG"
