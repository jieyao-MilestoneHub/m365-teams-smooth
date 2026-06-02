"""The offline LLM and knowledge providers are deterministic and grounded."""

from __future__ import annotations

from app.adapters.knowledge.fake_knowledge import FakeKnowledgeProvider
from app.adapters.llm.fake_llm import FakeLLMProvider


def test_fake_llm_is_deterministic() -> None:
    llm = FakeLLMProvider()
    out = llm.complete("Draft a reply\nsecond line")
    assert out == llm.complete("Draft a reply\nsecond line")
    assert "Draft a reply" in out


def test_fake_knowledge_grounds_by_keyword() -> None:
    kb = FakeKnowledgeProvider()
    facts = kb.ground("promise SSO is GA by next week")
    assert facts, "expected a grounded fact for a GA promise"
    assert facts[0].citation == "GA Readiness Policy §2.1"
    assert facts[0].source_id


def test_fake_knowledge_respects_top_k_and_misses() -> None:
    kb = FakeKnowledgeProvider()
    assert kb.ground("vendor access scope", top_k=1)[:1]  # at least one access fact
    assert kb.ground("something entirely unrelated") == []
