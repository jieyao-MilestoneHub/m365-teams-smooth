"""The offline ``KnowledgePort`` implementation — the default Microsoft IQ stand-in for local runs.

It grounds queries against the public-safe governance corpus in ``assets/knowledge-corpus/`` (no
confidential data) using the BM25-lite ranker in ``corpus``. Because it chunks and cites the same
documents the live Foundry IQ index is built from, offline citations are real policy prose with real
section titles — identical in form to live grounding. The same ``KnowledgePort`` is satisfied by the
managed knowledge layer (``FoundryIqKnowledgeProvider``) with no change to the impact node or graph.
"""

from __future__ import annotations

from pathlib import Path

from app.adapters.knowledge.corpus import Corpus, CorpusChunk, claim_for, load_corpus
from app.domain import GroundedFact
from app.ports.knowledge import KnowledgePort

# assets/knowledge-corpus lives at the repo root; this file is backend/app/adapters/knowledge/.
_DEFAULT_CORPUS_DIR = Path(__file__).resolve().parents[4] / "assets" / "knowledge-corpus"


class LocalCorpusKnowledgeProvider(KnowledgePort):
    """Retrieves cited facts from the local governance corpus via BM25-lite scoring."""

    def __init__(
        self,
        *,
        corpus_dir: Path | None = None,
        chunks: list[CorpusChunk] | None = None,
    ) -> None:
        loaded = chunks if chunks is not None else load_corpus(corpus_dir or _DEFAULT_CORPUS_DIR)
        self._corpus = Corpus(loaded)

    def ground(self, query: str, *, top_k: int = 3) -> list[GroundedFact]:
        # Never cite a superseded policy as authority, even when it ranks: filter, then take top_k.
        facts = [
            GroundedFact(claim=claim_for(chunk), source_id=chunk.doc_id, citation=chunk.title)
            for chunk, _score in self._corpus.search(query)
            if not chunk.superseded
        ]
        return facts[:top_k]
