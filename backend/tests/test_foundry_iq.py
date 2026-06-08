"""The real Foundry IQ knowledge provider: reference -> cited GroundedFact mapping.

Uses an injected stub retrieval client (no network), mirroring the injected-client style of the real
GitHub adapter test. Exercises the real request construction while stubbing the transport.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import cast

from azure.search.documents.knowledgebases import KnowledgeBaseRetrievalClient

from app.adapters.knowledge.foundry_iq import FoundryIqKnowledgeProvider


@dataclass
class _StubRef:
    id: str
    doc_key: str | None
    source_data: dict[str, object]


@dataclass
class _StubResult:
    references: list[_StubRef] | None


@dataclass
class _StubClient:
    result: _StubResult
    calls: list[object] = field(default_factory=list)

    def retrieve(self, *, retrieval_request: object) -> _StubResult:
        self.calls.append(retrieval_request)
        return self.result


def _provider(result: _StubResult) -> FoundryIqKnowledgeProvider:
    return FoundryIqKnowledgeProvider(
        endpoint="https://example.search.windows.net",
        knowledge_base_name="kb",
        knowledge_source_name="ks",
        client=cast(KnowledgeBaseRetrievalClient, _StubClient(result)),
    )


def test_ground_maps_references_to_cited_facts() -> None:
    result = _StubResult(
        references=[
            _StubRef(
                id="0",
                doc_key="doc-1",
                source_data={
                    "content": "No GA before the security review completes.",
                    "title": "GA Policy",
                },
            ),
            _StubRef(
                id="1",
                doc_key="doc-2",
                source_data={"page_chunk": "Vendor access is least-privilege and time-boxed."},
            ),
        ]
    )

    facts = _provider(result).ground("ga promise")

    assert len(facts) == 2
    assert facts[0].claim == "No GA before the security review completes."
    assert facts[0].source_id == "doc-1"
    assert facts[0].citation == "GA Policy [ref 0]"
    # Falls back to the reference id for the citation when no title field is present.
    assert facts[1].claim == "Vendor access is least-privilege and time-boxed."
    assert facts[1].source_id == "doc-2"
    assert facts[1].citation == "ref 1"


def test_ground_respects_top_k() -> None:
    result = _StubResult(
        references=[
            _StubRef(id=str(i), doc_key=f"doc-{i}", source_data={"content": f"fact {i}"})
            for i in range(5)
        ]
    )

    assert len(_provider(result).ground("q", top_k=2)) == 2


def test_ground_skips_references_without_text() -> None:
    result = _StubResult(
        references=[
            _StubRef(id="0", doc_key="doc-1", source_data={"score": 0.9}),  # no text field
            _StubRef(id="1", doc_key="doc-2", source_data={"content": "real fact"}),
        ]
    )

    facts = _provider(result).ground("q")

    assert len(facts) == 1
    assert facts[0].claim == "real fact"


def test_ground_handles_no_references() -> None:
    assert _provider(_StubResult(references=None)).ground("q") == []


def test_reasoning_effort_is_configurable_and_defaults_to_medium() -> None:
    from azure.search.documents.knowledgebases.models import (
        KnowledgeRetrievalLowReasoningEffort,
        KnowledgeRetrievalMediumReasoningEffort,
    )

    def _effort_for(value: str | None) -> object:
        stub = _StubClient(_StubResult(references=[]))
        kwargs = {} if value is None else {"reasoning_effort": value}
        FoundryIqKnowledgeProvider(
            endpoint="https://example.search.windows.net",
            knowledge_base_name="kb",
            knowledge_source_name="ks",
            client=cast(KnowledgeBaseRetrievalClient, stub),
            **kwargs,  # type: ignore[arg-type]
        ).ground("q")
        return stub.calls[0].retrieval_reasoning_effort  # type: ignore[attr-defined]

    assert isinstance(_effort_for("low"), KnowledgeRetrievalLowReasoningEffort)
    assert isinstance(_effort_for(None), KnowledgeRetrievalMediumReasoningEffort)
    # An unknown value falls back to the medium default rather than raising.
    assert isinstance(_effort_for("bogus"), KnowledgeRetrievalMediumReasoningEffort)
