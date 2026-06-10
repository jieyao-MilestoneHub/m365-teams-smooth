"""Offline retrieval over the governance corpus — pure, deterministic, no SDK or framework imports.

One responsibility: load ``assets/knowledge-corpus/*.md`` into ranked chunks and score a query
against them with a real BM25-lite ranker (not a stub). It backs ``LocalCorpusKnowledgeProvider`` so
the credential-free path grounds against the *same* documents the live Foundry IQ index is built
from, producing citations identical in form to live ones. No external libraries — the scorer is
implemented here so the offline path carries zero extra dependencies.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from app.adapters.knowledge.markdown import chunk_markdown, slugify

# BM25 parameters (the usual defaults). ``k1`` controls term-frequency saturation; ``b`` controls
# length normalization. ``_TAG_BOOST`` nudges a chunk whose path/heading tags match query terms.
_K1 = 1.5
_B = 0.75
_TAG_BOOST = 0.4
_MAX_CLAIM_CHARS = 360

# A tiny stopword set keeps generic words from dominating the score; deliberately minimal so the
# ranker stays transparent and deterministic.
_STOPWORDS = frozenset(
    "a an and are as at be by for from in into is it of on or our that the to with "
    "must should when which while who whom whose".split()
)


def _tokenize(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) > 1 and t not in _STOPWORDS]


@dataclass(frozen=True)
class CorpusChunk:
    """One ``##`` section of a corpus document, ready to score and cite."""

    doc_id: str
    title: str  # "<doc title> — <heading>" — matches the live index's citation title
    heading: str
    text: str  # the ``page_chunk`` ("## heading\n body"), as the live index stores it
    tags: tuple[str, ...]  # path-segment + heading keywords, for the tag-match boost
    tokens: tuple[str, ...] = field(default=(), compare=False)


def _claim_of(text: str) -> str:
    """The displayed claim: the chunk body without its ``## heading`` line, whitespace-collapsed."""
    body = re.sub(r"^##\s+.*\n?", "", text, count=1)
    return re.sub(r"\s+", " ", body).strip()[:_MAX_CLAIM_CHARS]


def load_corpus(root: Path) -> list[CorpusChunk]:
    """Load every corpus markdown file (except READMEs) into scored-ready chunks.

    Chunking reuses ``markdown.chunk_markdown`` so boundaries, titles, and the ``page_chunk`` shape
    match the live seed script exactly. The deprecated/distractor documents are loaded too — good
    retrieval must rank the current policy above them, mirroring the live retrieval eval.
    """
    chunks: list[CorpusChunk] = []
    for path in sorted(root.rglob("*.md")):
        if path.name.lower() == "readme.md":
            continue
        doc_title, sections = chunk_markdown(path.read_text(encoding="utf-8"))
        stem_tags = _tokenize(path.stem.replace("-", " "))
        for i, (heading, page_chunk) in enumerate(sections):
            title = f"{doc_title} — {heading}" if doc_title else heading
            tags = tuple(dict.fromkeys(stem_tags + _tokenize(heading)))
            chunks.append(
                CorpusChunk(
                    doc_id=f"{slugify(path.stem)}-{i}",
                    title=title,
                    heading=heading,
                    text=page_chunk,
                    tags=tags,
                    tokens=tuple(_tokenize(f"{title} {page_chunk}")),
                )
            )
    return chunks


class Corpus:
    """A scored corpus: precomputes document frequencies once, then ranks queries with BM25-lite."""

    def __init__(self, chunks: list[CorpusChunk]) -> None:
        self._chunks = chunks
        n = len(chunks) or 1
        df: Counter[str] = Counter()
        for chunk in chunks:
            df.update(set(chunk.tokens))
        # BM25 idf with the +1 guard so it never goes negative for very common terms.
        self._idf = {
            term: math.log(1 + (n - freq + 0.5) / (freq + 0.5)) for term, freq in df.items()
        }
        lengths = [len(c.tokens) for c in chunks]
        self._avgdl = (sum(lengths) / len(lengths)) if lengths else 0.0

    def score(self, query_terms: list[str], chunk: CorpusChunk) -> float:
        """BM25-lite over the chunk's tokens, plus a bounded boost for tag matches."""
        if not chunk.tokens:
            return 0.0
        tf = Counter(chunk.tokens)
        dl = len(chunk.tokens)
        denom_norm = _K1 * (1 - _B + _B * dl / self._avgdl) if self._avgdl else _K1
        total = 0.0
        for term in query_terms:
            freq = tf.get(term, 0)
            if freq:
                idf = self._idf.get(term, 0.0)
                total += idf * (freq * (_K1 + 1)) / (freq + denom_norm)
        tag_hits = sum(1 for term in set(query_terms) if term in chunk.tags)
        return total + _TAG_BOOST * tag_hits

    def search(self, query: str, top_k: int) -> list[tuple[CorpusChunk, float]]:
        """Rank chunks for ``query``; drop zero-score chunks so unrelated queries return nothing."""
        terms = _tokenize(query)
        scored = [(c, self.score(terms, c)) for c in self._chunks]
        ranked = sorted((cs for cs in scored if cs[1] > 0), key=lambda cs: cs[1], reverse=True)
        return ranked[:top_k]


def claim_for(chunk: CorpusChunk) -> str:
    """The human-readable claim text for a chunk (exposed for the provider and tests)."""
    return _claim_of(chunk.text)
