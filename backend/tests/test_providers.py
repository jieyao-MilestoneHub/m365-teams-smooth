"""The offline LLM provider is deterministic. (Knowledge grounding: see test_local_corpus.py.)"""

from __future__ import annotations

from app.adapters.llm.fake_llm import FakeLLMProvider


def test_fake_llm_is_deterministic() -> None:
    llm = FakeLLMProvider()
    out = llm.complete("Draft a reply\nsecond line")
    assert out == llm.complete("Draft a reply\nsecond line")
    assert "Draft a reply" in out
