"""Real Outlook adapter (read-only evidence path) over Microsoft Graph.

Provides the *read* capabilities the Customer Promise trial relies on — the security-review date
(the decisive evidence: a review scheduled after a promised GA date) and calendar events — sourced
from a configured user's real calendar. Writes (create event, draft email) are intentionally NOT
performed: under DRY_RUN the base class predicts the effect, and a LIVE write is refused and
contained. Selected when ``outlook`` runs in ``real`` mode with Graph credentials configured.
"""

from __future__ import annotations

from app.adapters.integrations.base import BaseIntegrationAdapter
from app.adapters.integrations.graph import GraphClient
from app.domain import (
    Capability,
    CapabilityKind,
    ExecutionStep,
    PredictedEffect,
    RollbackHint,
)
from app.domain.errors import IntegrationError
from app.ports.integration import ReadQuery, ReadResult

_SYSTEM = "outlook"


class RealOutlookAdapter(BaseIntegrationAdapter):
    """Reads a configured user's Outlook calendar via Graph; writes stay dry-run only."""

    def __init__(self, graph: GraphClient, calendar_upn: str) -> None:
        self._graph = graph
        self._upn = calendar_upn

    @property
    def system(self) -> str:
        return _SYSTEM

    def _capabilities(self) -> list[Capability]:
        # Same capability surface as the mock so plans and the intake guard behave identically.
        return [
            Capability(system=_SYSTEM, name="outlook.read_events", kind=CapabilityKind.READ),
            Capability(
                system=_SYSTEM, name="outlook.read_security_review", kind=CapabilityKind.READ
            ),
            Capability(
                system=_SYSTEM,
                name="outlook.create_event",
                kind=CapabilityKind.WRITE,
                params_schema={"required": ["title", "start"]},
            ),
            Capability(
                system=_SYSTEM,
                name="outlook.draft_email",
                kind=CapabilityKind.WRITE,
                params_schema={"required": ["to", "subject"]},
            ),
        ]

    def _events(self) -> list[dict[str, object]]:
        data = self._graph.get(
            f"/users/{self._upn}/events",
            **{"$select": "subject,start,end", "$top": "50"},
        )
        value = data.get("value", [])
        return list(value) if isinstance(value, list) else []

    @staticmethod
    def _when(event: dict[str, object], key: str) -> str | None:
        slot = event.get(key)
        when = slot.get("dateTime") if isinstance(slot, dict) else None
        return when if isinstance(when, str) else None

    @classmethod
    def _day(cls, event: dict[str, object]) -> str | None:
        when = cls._when(event, "start")
        return when[:10] if when and len(when) >= 10 else None

    def _read(self, query: ReadQuery) -> ReadResult:
        if query.capability == "outlook.read_security_review":
            subject_kw = str(query.params.get("subject", "")).lower()
            earliest: str | None = None
            for event in self._events():
                subject = str(event.get("subject", "")).lower()
                if "security" in subject and "review" in subject and (
                    not subject_kw or subject_kw in subject
                ):
                    day = self._day(event)
                    if day and (earliest is None or day < earliest):
                        earliest = day
            return ReadResult(
                capability=query.capability,
                data={"subject": subject_kw or "sso", "review_date": earliest},
            )
        if query.capability == "outlook.read_events":
            events = [
                {
                    "title": event.get("subject"),
                    "start": self._when(event, "start"),
                    "end": self._when(event, "end"),
                }
                for event in self._events()
            ]
            return ReadResult(capability=query.capability, data={"events": events})
        raise IntegrationError(f"{_SYSTEM}: unknown read capability '{query.capability}'")

    def _predict(self, step: ExecutionStep, before: dict[str, object]) -> PredictedEffect:
        if step.capability.name == "outlook.create_event":
            return PredictedEffect(summary="would create a calendar event", diff=dict(step.params))
        return PredictedEffect(summary="would draft an email (not sent)", diff=dict(step.params))

    def _apply(self, step: ExecutionStep) -> dict[str, object]:
        # Read-only evidence adapter: real writes are out of scope; execution runs in DRY_RUN.
        raise IntegrationError(f"{_SYSTEM}: real writes are disabled (dry-run only)")

    def _fetch_before(self, step: ExecutionStep) -> dict[str, object]:
        return {}

    def _rollback(self, step: ExecutionStep, before: dict[str, object]) -> RollbackHint:
        return RollbackHint(
            step_id=step.step_id,
            system=_SYSTEM,
            instruction="delete the created event/draft to restore the prior state",
            params=before,
        )
