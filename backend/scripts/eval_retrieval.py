"""Retrieval-quality eval for the contextual-retrieval knowledge base.

Runs the **production** retrieval path (`FoundryIqKnowledgeProvider.ground`, hybrid BM25 + vector +
semantic rerank over the contextual index) for each trial's grounding query and checks that the
intended **target** policy ranks #1 — above the deliberately-seeded **adversarial near-miss** (a
same-vocabulary distractor, a deprecated policy version, a different project's notes). This is the
concrete proof that retrieval discriminates, rather than "grabbing chunks".

Run (against the live, seeded index):  ``uv run python -m scripts.eval_retrieval``
Auth is keyless (``DefaultAzureCredential``); exits non-zero if any target fails to rank #1.
"""

from __future__ import annotations

import os
import sys

from app.adapters.knowledge.foundry_iq import FoundryIqKnowledgeProvider

ENDPOINT = os.environ.get(
    "KNOWLEDGE_SEARCH_ENDPOINT", "https://iqs-search-mm65ytt5g64nw.search.windows.net"
)
BASE = os.environ.get("KNOWLEDGE_BASE_NAME", "governance-knowledge-base")
SOURCE = os.environ.get("KNOWLEDGE_SOURCE_NAME", "governance-knowledge-source")
EFFORT = os.environ.get("KNOWLEDGE_REASONING_EFFORT", "medium")

# (label, query, target substring, exclude-from-target, near-miss substrings that must not outrank).
# Queries mirror the gatherer/impact grounding calls (backend/app/agent/gatherers.py).
CASES = [
    ("Reschedule", "schedule change controlled coordinated milestone date",
     "Release & Change Management Policy", ("DEPRECATED", "v1"),
     ("Scheduling Guidelines", "DEPRECATED")),
    ("Meeting Actions", "meeting follow-through action item owner due date accountability",
     "Meeting Follow-through Policy", (), ("All-Hands", "Project Y")),
    ("Weekly Report", "status reporting weekly cadence single source of record",
     "Status Reporting Policy", (), ("Dashboard", "Power BI")),
    ("Customer Promise", "SSO GA promise security review sign-off",
     "Customer Commitment & GA Readiness Policy", (), ()),
    ("Vendor Access", "vendor access least privilege scope expiry",
     "Third-Party Vendor & Contractor Access Policy", (), ()),
]


def _rank(citations: list[str], includes: str, excludes: tuple[str, ...] = ()) -> int | None:
    for i, c in enumerate(citations):
        if includes in c and not any(x in c for x in excludes):
            return i
    return None


def main() -> None:
    provider = FoundryIqKnowledgeProvider(
        endpoint=ENDPOINT, knowledge_base_name=BASE, knowledge_source_name=SOURCE,
        reasoning_effort=EFFORT,
    )
    print(f"knowledge base: {BASE} (reasoning_effort={EFFORT})\n")
    failures = 0
    for label, query, target, target_ex, near_misses in CASES:
        facts = provider.ground(query, top_k=5)
        citations = [f.citation for f in facts]
        t_rank = _rank(citations, target, target_ex)
        nm_rank = min(
            (r for nm in near_misses if (r := _rank(citations, nm)) is not None), default=None
        )
        ok = t_rank == 0 and (nm_rank is None or nm_rank > t_rank)
        failures += not ok
        print(f"[{'PASS' if ok else 'FAIL'}] {label}: {query!r}")
        for i, c in enumerate(citations):
            mark = "→" if i == t_rank else (" ✗" if nm_rank is not None and i == nm_rank else "  ")
            print(f"    {mark} #{i + 1} {c}")
        if t_rank is None:
            print(f"    (target {target!r} not in top {len(citations)})")
        print()
    print(f"{len(CASES) - failures}/{len(CASES)} targets ranked #1 above their near-miss")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
