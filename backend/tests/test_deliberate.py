"""The deliberators capture node reasoning with honest provenance and degrade gracefully."""

from __future__ import annotations

from app.agent.deliberate import LlmDeliberator, OfflineDeliberator, record
from app.domain import SOURCE_LLM, SOURCE_OFFLINE_STUB
from app.ports.llm import LLMProvider


class _StubLLM(LLMProvider):
    def __init__(self, reply: str = "Because the factors warrant approval.") -> None:
        self.reply = reply
        self.calls: list[tuple[str, str | None]] = []

    def complete(self, prompt: str, *, system: str | None = None) -> str:
        self.calls.append((prompt, system))
        return self.reply


class _BrokenLLM(LLMProvider):
    def complete(self, prompt: str, *, system: str | None = None) -> str:
        raise RuntimeError("model unavailable")


def test_offline_deliberator_records_context_as_stub() -> None:
    entry = OfflineDeliberator().deliberate(node="policy", role="", context="Risk 80 (high).")
    assert entry.node == "policy"
    assert entry.rationale == "Risk 80 (high)."
    assert entry.source == SOURCE_OFFLINE_STUB


def test_llm_deliberator_reuses_role_reasoning_without_calling() -> None:
    llm = _StubLLM()
    entry = LlmDeliberator(llm).deliberate(
        node="impact", role="prosecutor", context="2 findings.", reasoning="The slip risks X."
    )
    assert entry.source == SOURCE_LLM
    assert entry.rationale == "The slip risks X."
    assert llm.calls == []  # reused role prose, no extra call


def test_llm_deliberator_explains_context_when_no_prior_reasoning() -> None:
    llm = _StubLLM()
    entry = LlmDeliberator(llm).deliberate(node="policy", role="", context="Risk 80 (high).")
    assert entry.source == SOURCE_LLM
    assert entry.rationale == "Because the factors warrant approval."
    assert len(llm.calls) == 1
    assert llm.calls[0][1] is not None  # a node-specific system prompt was used


def test_llm_deliberator_falls_back_to_stub_on_failure() -> None:
    entry = LlmDeliberator(_BrokenLLM()).deliberate(node="intake", role="", context="Parsed 1.")
    assert entry.source == SOURCE_OFFLINE_STUB  # honest: the LLM did not produce this
    assert entry.rationale == "Parsed 1."


def test_record_appends_preserving_prior_entries() -> None:
    state = {"deliberations": [{"node": "intake", "role": "", "rationale": "a", "source": "llm"}]}
    entry = OfflineDeliberator().deliberate(node="impact", role="prosecutor", context="b")
    appended = record(state, entry)  # type: ignore[arg-type]
    assert [d["node"] for d in appended] == ["intake", "impact"]
