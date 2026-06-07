"""Mock Outlook adapter: calendar events, security-review lookup, event creation, email drafts.

Returns realistic in-memory data so the trials run with zero credentials. Email is only ever
*drafted*, never sent — the safe-alternative flow for the Customer Promise trial relies on this.
"""

from __future__ import annotations

from app.adapters.integrations.base import BaseIntegrationAdapter
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


class MockOutlookAdapter(BaseIntegrationAdapter):
    """In-memory Outlook stand-in."""

    def __init__(self) -> None:
        # A security review for SSO lands on the 18th — after a promised 17th (Customer Promise).
        # The board review occupies the 16th, so a reschedule targeting that day collides.
        self._events: list[dict[str, object]] = [
            {
                "title": "Board review",
                "start": "2026-06-16T09:00:00Z",
                "end": "2026-06-16T10:00:00Z",
            },
        ]
        self._security_reviews: dict[str, str] = {"sso": "2026-06-18"}
        self._drafts: list[dict[str, object]] = []

    @property
    def system(self) -> str:
        return _SYSTEM

    def _capabilities(self) -> list[Capability]:
        return [
            Capability(system=_SYSTEM, name="outlook.read_events", kind=CapabilityKind.READ),
            Capability(
                system=_SYSTEM, name="outlook.read_security_review", kind=CapabilityKind.READ
            ),
            Capability(
                system=_SYSTEM,
                name="outlook.create_event",
                kind=CapabilityKind.WRITE,
                params_schema={
                    "required": ["title", "start"],
                    "properties": {"start": {"format": "date"}},
                },
            ),
            Capability(
                system=_SYSTEM,
                name="outlook.draft_email",
                kind=CapabilityKind.WRITE,
                params_schema={"required": ["to", "subject"]},
            ),
        ]

    def _read(self, query: ReadQuery) -> ReadResult:
        if query.capability == "outlook.read_events":
            return ReadResult(capability=query.capability, data={"events": list(self._events)})
        if query.capability == "outlook.read_security_review":
            subject = str(query.params.get("subject", "")).lower()
            return ReadResult(
                capability=query.capability,
                data={"subject": subject, "review_date": self._security_reviews.get(subject)},
            )
        raise IntegrationError(f"{_SYSTEM}: unknown read capability '{query.capability}'")

    def _predict(self, step: ExecutionStep, before: dict[str, object]) -> PredictedEffect:
        if step.capability.name == "outlook.create_event":
            return PredictedEffect(summary="would create a calendar event", diff=dict(step.params))
        return PredictedEffect(summary="would draft an email (not sent)", diff=dict(step.params))

    def _apply(self, step: ExecutionStep) -> dict[str, object]:
        if step.capability.name == "outlook.create_event":
            event = dict(step.params)
            self._events.append(event)
            return {"created_event": event}
        if step.capability.name == "outlook.draft_email":
            draft = {**step.params, "status": "draft", "sent": False}
            self._drafts.append(draft)
            return {"draft": draft}
        raise IntegrationError(f"{_SYSTEM}: unknown write capability '{step.capability.name}'")

    def _fetch_before(self, step: ExecutionStep) -> dict[str, object]:
        if step.capability.name == "outlook.draft_email":
            return {"drafts": len(self._drafts)}
        return {"events": len(self._events)}

    def _rollback(self, step: ExecutionStep, before: dict[str, object]) -> RollbackHint:
        return RollbackHint(
            step_id=step.step_id,
            system=_SYSTEM,
            instruction="delete the created event/draft to restore the prior state",
            params=before,
        )
