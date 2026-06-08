"""Offline knowledge provider — the default Microsoft IQ stand-in for local runs.

It grounds queries against a small, public-safe governance corpus (no confidential data), returning
cited facts. The same `KnowledgePort` is later satisfied by a managed knowledge layer (Foundry IQ).
"""

from __future__ import annotations

from app.domain import GroundedFact
from app.ports.knowledge import KnowledgePort

# (keywords, fact) pairs. A fact is surfaced when any of its keywords appears in the query. The
# citations mirror the live Foundry IQ corpus titles (assets/knowledge-corpus/) so local and live
# ground the same policies.
_DEFAULT_CORPUS: list[tuple[tuple[str, ...], GroundedFact]] = [
    (
        ("ga", "general availability", "promise", "sso"),
        GroundedFact(
            claim=(
                "A capability cannot be declared generally available before its "
                "security review completes."
            ),
            source_id="policy/ga-readiness",
            citation="Customer Commitment & GA Readiness Policy — No commitment before sign-off",
        ),
    ),
    (
        ("access", "vendor", "guest", "least privilege", "scope"),
        GroundedFact(
            claim=(
                "External access should be least-privilege and time-boxed, with an "
                "explicit revoke date."
            ),
            source_id="policy/vendor-access",
            citation="Third-Party Vendor & Contractor Access Policy — Time-bound access",
        ),
    ),
    (
        ("launch", "milestone", "slip", "schedule"),
        GroundedFact(
            claim=(
                "Moving a launch milestone requires updating dependent schedules and "
                "pending communications."
            ),
            source_id="policy/release-change-management",
            citation="Release & Change Management Policy — Coordinated downstream updates",
        ),
    ),
    (
        ("renewal", "customer", "commitment"),
        GroundedFact(
            claim="Commitments affecting an at-risk renewal require account-owner sign-off.",
            source_id="policy/ga-readiness",
            citation="Customer Commitment & GA Readiness Policy — Approval and quorum",
        ),
    ),
    (
        ("report", "status", "weekly", "cadence"),
        GroundedFact(
            claim=(
                "Status reports follow a weekly cadence and post to the project channel "
                "as the single source of record."
            ),
            source_id="policy/status-reporting",
            citation="Status Reporting Policy — Weekly cadence, single source",
        ),
    ),
    (
        ("action item", "follow-up", "follow-through", "meeting", "standup"),
        GroundedFact(
            claim=(
                "Action items agreed in a meeting must be tracked with an owner and a due "
                "date, not left in the discussion."
            ),
            source_id="policy/meeting-follow-through",
            citation="Meeting Follow-through Policy — Action items must be tracked, not remembered",
        ),
    ),
]


class FakeKnowledgeProvider(KnowledgePort):
    """Keyword-matches a query against an in-memory corpus and returns cited facts."""

    def __init__(self, corpus: list[tuple[tuple[str, ...], GroundedFact]] | None = None) -> None:
        self._corpus = corpus if corpus is not None else _DEFAULT_CORPUS

    def ground(self, query: str, *, top_k: int = 3) -> list[GroundedFact]:
        q = query.lower()
        hits = [fact for keywords, fact in self._corpus if any(k in q for k in keywords)]
        return hits[:top_k]
