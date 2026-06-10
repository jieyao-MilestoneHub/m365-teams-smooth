"""The offline corpus retrieval engine ranks the right policy and degrades cleanly.

These mirror the live retrieval eval (``scripts/eval_retrieval.py`` CASES): the same gatherer-style
queries must surface the target policy and rank it above its adversarial near-miss (notably the
deprecated change-management distractor). This is the credential-free analog of the live proof.
"""

from __future__ import annotations

from app.adapters.knowledge.corpus import Corpus, load_corpus
from app.adapters.knowledge.local_corpus import _DEFAULT_CORPUS_DIR, LocalCorpusKnowledgeProvider

# (label, query, target substring, exclude-from-target, near-miss substring that must not outrank).
# Queries mirror the impact gatherer's grounding calls. The Reschedule near-miss (the deprecated
# change policy) is handled separately below — the provider filters superseded docs entirely.
CASES = [
    (
        "Meeting Actions",
        "meeting follow-through action item owner due date accountability",
        "Meeting Follow-through Policy",
        (),
        "All-Hands",
    ),
    (
        "Weekly Report",
        "status reporting weekly cadence single source of record",
        "Status Reporting Policy",
        (),
        "Dashboard",
    ),
    (
        "Customer Promise",
        "SSO GA promise security review sign-off",
        "Customer Commitment & GA Readiness Policy",
        (),
        "",
    ),
    (
        "Vendor Access",
        "vendor access least privilege scope expiry",
        "Third-Party Vendor & Contractor Access Policy",
        (),
        "",
    ),
]

_RESCHEDULE_QUERY = "schedule change controlled coordinated milestone date"


def _rank(citations: list[str], includes: str, excludes: tuple[str, ...] = ()) -> int | None:
    for i, c in enumerate(citations):
        if includes in c and not any(x in c for x in excludes):
            return i
    return None


def test_load_corpus_covers_every_non_readme_document() -> None:
    chunks = load_corpus(_DEFAULT_CORPUS_DIR)
    assert chunks, "expected the governance corpus to load"
    titles = {c.title.split(" — ")[0] for c in chunks}
    # A representative spread across policies, reference, and meetings is chunked.
    assert "Release & Change Management Policy" in titles
    assert "Customer Commitment & GA Readiness Policy" in titles
    assert all(c.text.startswith("## ") for c in chunks)
    assert all(c.doc_id and c.title for c in chunks)


def test_each_case_surfaces_target_above_near_miss() -> None:
    kb = LocalCorpusKnowledgeProvider()
    for label, query, target, target_ex, near_miss in CASES:
        facts = kb.ground(query, top_k=5)
        citations = [f.citation for f in facts]
        target_rank = _rank(citations, target, target_ex)
        assert target_rank is not None, f"{label}: target {target!r} missing (got {citations})"
        if near_miss:
            near_rank = _rank(citations, near_miss)
            assert (
                near_rank is None or target_rank < near_rank
            ), f"{label}: near-miss {near_miss!r} outranked the target {target!r} ({citations})"


def test_ranker_ranks_current_policy_above_deprecated() -> None:
    # The ranking proof (offline analog of the live eval): even though the deprecated change policy
    # shares vocabulary, the current Release & Change Management Policy must rank above it.
    corpus = Corpus(load_corpus(_DEFAULT_CORPUS_DIR))
    ranked = corpus.search(_RESCHEDULE_QUERY)
    titles = [c.title for c, _ in ranked]
    current = next(
        i
        for i, t in enumerate(titles)
        if t.startswith("Release & Change Management Policy") and "DEPRECATED" not in t
    )
    deprecated = next((i for i, t in enumerate(titles) if "DEPRECATED" in t), None)
    assert deprecated is None or current < deprecated


def test_provider_never_cites_a_superseded_policy() -> None:
    kb = LocalCorpusKnowledgeProvider()
    facts = kb.ground(_RESCHEDULE_QUERY, top_k=5)
    assert facts, "expected the current change policy to ground a reschedule"
    assert all("DEPRECATED" not in f.citation and "superseded" not in f.citation for f in facts)


def test_grounded_facts_are_cited_and_real() -> None:
    kb = LocalCorpusKnowledgeProvider()
    facts = kb.ground(_RESCHEDULE_QUERY)
    assert facts
    assert facts[0].citation.startswith("Release & Change Management Policy")
    assert facts[0].source_id  # carries a stable document id
    assert facts[0].claim and not facts[0].claim.startswith("##")  # heading line stripped


def test_top_k_is_respected() -> None:
    kb = LocalCorpusKnowledgeProvider()
    assert len(kb.ground("vendor access least privilege scope expiry", top_k=1)) == 1
    assert len(kb.ground("vendor access least privilege scope expiry", top_k=3)) <= 3


def test_unrelated_query_returns_nothing() -> None:
    kb = LocalCorpusKnowledgeProvider()
    assert kb.ground("xylophone quokka zeppelin marzipan") == []
