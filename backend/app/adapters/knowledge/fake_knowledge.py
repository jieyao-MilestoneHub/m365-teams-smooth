"""Offline knowledge provider — the default Microsoft IQ stand-in for local runs.

It grounds queries against a small, public-safe governance corpus (no confidential data), returning
cited facts. The same `KnowledgePort` is later satisfied by a managed knowledge layer (Foundry IQ).
"""

from __future__ import annotations

from app.domain import GroundedFact
from app.ports.knowledge import KnowledgePort

# (keywords, fact) pairs. A fact is surfaced when any of its keywords appears in the query.
_DEFAULT_CORPUS: list[tuple[tuple[str, ...], GroundedFact]] = [
    (
        ("ga", "general availability", "promise", "sso"),
        GroundedFact(
            claim=(
                "A capability cannot be declared generally available before its "
                "security review completes."
            ),
            source_id="policy/ga-readiness",
            citation="GA Readiness Policy §2.1",
        ),
    ),
    (
        ("access", "vendor", "guest", "least privilege", "scope"),
        GroundedFact(
            claim=(
                "External access should be least-privilege and time-boxed, with an "
                "explicit revoke date."
            ),
            source_id="policy/access-control",
            citation="Access Control Policy §4.3",
        ),
    ),
    (
        ("launch", "milestone", "slip", "schedule"),
        GroundedFact(
            claim=(
                "Moving a launch milestone requires updating dependent schedules and "
                "pending communications."
            ),
            source_id="playbook/launch",
            citation="Launch Playbook §3.2",
        ),
    ),
    (
        ("renewal", "customer", "commitment"),
        GroundedFact(
            claim="Commitments affecting an at-risk renewal require account-owner sign-off.",
            source_id="policy/commercial",
            citation="Commercial Commitments Policy §1.4",
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
            citation="Meeting Follow-through Policy §1.2",
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
