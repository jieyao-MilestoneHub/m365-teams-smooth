"""Subject → targeted grounding phrase: one source of truth for knowledge retrieval.

Each phrase is tuned so the knowledge base ranks the intended governance policy above its
adversarial near-misses — validated by ``backend/scripts/eval_retrieval.py``. Both the impact node
and the per-subject gatherers ground through these phrases, so a bare user request (which the real
Foundry IQ retrieval ranks poorly) never drives grounding for a classified change, and retrieval
stays consistent across the two call sites.

Grounding is *citations only* — it never produces tags and never affects risk, quorum, or the
verdict. Adding a subject is one dict entry here (open/closed); no other module changes.
"""

from __future__ import annotations

# Keys mirror the GATHERERS subjects in app/agent/gatherers.py and Change.subject from intake.
GROUNDING_QUERIES: dict[str, str] = {
    "launch": "schedule change controlled coordinated milestone date",
    "sso-ga": "SSO GA promise security review sign-off",
    "project-access": "vendor access least privilege scope expiry",
    "meeting-actions": "meeting follow-through action item owner due date accountability",
    "weekly-report": "status reporting weekly cadence single source of record",
}


def grounding_query(subject: str | None, raw_request: str) -> str:
    """The targeted phrase for ``subject``, or ``raw_request`` when unclassified/unknown."""
    if subject is None:
        return raw_request
    return GROUNDING_QUERIES.get(subject, raw_request)
