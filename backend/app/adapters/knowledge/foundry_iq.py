"""Real knowledge provider: Foundry IQ agentic retrieval over Azure AI Search.

Satisfies the same ``KnowledgePort`` as the offline fake, but grounds queries against a
managed Azure AI Foundry knowledge base, returning cited facts. Authentication is keyless
(``DefaultAzureCredential`` — ``az login`` locally, managed identity when hosted); no key is
read from config. Selected in the composition root only when a knowledge endpoint is set.
"""

from __future__ import annotations

from azure.core.credentials import TokenCredential
from azure.identity import DefaultAzureCredential
from azure.search.documents.knowledgebases import KnowledgeBaseRetrievalClient
from azure.search.documents.knowledgebases.models import (
    KnowledgeBaseMessage,
    KnowledgeBaseMessageTextContent,
    KnowledgeBaseRetrievalRequest,
    KnowledgeRetrievalLowReasoningEffort,
    SearchIndexKnowledgeSourceParams,
)

from app.domain import GroundedFact
from app.ports.knowledge import KnowledgePort

# Document fields, most-preferred first, to use as a fact's claim text.
_CLAIM_KEYS = ("content", "page_chunk", "chunk", "text", "body", "summary", "description")
# Document fields to use as a human-readable citation title.
_TITLE_KEYS = ("title", "name", "heading", "source")
_MAX_CLAIM_CHARS = 600


class FoundryIqKnowledgeProvider(KnowledgePort):
    """Grounds queries against a Foundry IQ knowledge base and returns cited facts."""

    def __init__(
        self,
        *,
        endpoint: str,
        knowledge_base_name: str,
        knowledge_source_name: str,
        timeout: float | None = None,
        credential: TokenCredential | None = None,
        client: KnowledgeBaseRetrievalClient | None = None,
    ) -> None:
        self._knowledge_source_name = knowledge_source_name
        self._timeout = timeout
        self._client = client or KnowledgeBaseRetrievalClient(
            endpoint=endpoint,
            knowledge_base_name=knowledge_base_name,
            credential=credential or DefaultAzureCredential(),
        )

    def ground(self, query: str, *, top_k: int = 3) -> list[GroundedFact]:
        """Retrieve up to ``top_k`` cited facts for ``query`` from the knowledge base."""
        request = KnowledgeBaseRetrievalRequest(
            messages=[
                KnowledgeBaseMessage(
                    role="user", content=[KnowledgeBaseMessageTextContent(text=query)]
                )
            ],
            knowledge_source_params=[
                SearchIndexKnowledgeSourceParams(
                    knowledge_source_name=self._knowledge_source_name,
                    include_references=True,
                    include_reference_source_data=True,
                )
            ],
            include_activity=False,
            retrieval_reasoning_effort=KnowledgeRetrievalLowReasoningEffort(),
        )
        # Bound the outbound search call; azure-core honors a per-operation timeout kwarg.
        if self._timeout is not None:
            result = self._client.retrieve(retrieval_request=request, timeout=self._timeout)
        else:
            result = self._client.retrieve(retrieval_request=request)
        references = result.references or []

        facts: list[GroundedFact] = []
        for ref in references[:top_k]:
            source_data: dict[str, object] = getattr(ref, "source_data", None) or {}
            claim = _claim_of(source_data)
            if not claim:
                continue
            ref_id = str(getattr(ref, "id", "") or "")
            source_id = str(getattr(ref, "doc_key", None) or ref_id)
            facts.append(
                GroundedFact(
                    claim=claim, source_id=source_id, citation=_citation_of(source_data, ref_id)
                )
            )
        return facts


def _claim_of(source_data: dict[str, object]) -> str:
    """Pick the most relevant text from a reference's source data as the fact's claim."""
    for key in _CLAIM_KEYS:
        value = source_data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:_MAX_CLAIM_CHARS]
    longest = max(
        (v for v in source_data.values() if isinstance(v, str) and v.strip()),
        key=len,
        default="",
    )
    return longest.strip()[:_MAX_CLAIM_CHARS]


def _citation_of(source_data: dict[str, object], ref_id: str) -> str:
    """Build a human-readable citation from a title field and the reference id."""
    for key in _TITLE_KEYS:
        value = source_data.get(key)
        if isinstance(value, str) and value.strip():
            return f"{value.strip()} [ref {ref_id}]" if ref_id else value.strip()
    return f"ref {ref_id}" if ref_id else ""
