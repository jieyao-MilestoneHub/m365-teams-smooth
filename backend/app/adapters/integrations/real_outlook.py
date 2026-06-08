"""Real Outlook adapter over Microsoft Graph: reads calendar evidence and performs contained writes.

Reads provide the evidence the Customer Promise / Reschedule trials rely on — the security-review
date (a review scheduled after a promised GA date) and calendar events — from a configured user's
real calendar. Writes are contained: a LIVE ``create_event`` creates a real calendar event and
``draft_email`` creates a real *draft* (left in Drafts, never sent — the app is not granted
``Mail.Send``). Under DRY_RUN the base class predicts the effect instead. Selected when ``outlook``
runs in ``real`` mode with Graph credentials configured.
"""

from __future__ import annotations

from datetime import datetime

from app.adapters.integrations.base import BaseIntegrationAdapter
from app.adapters.integrations.graph import GraphClient
from app.adapters.integrations.retry import RetryPolicy
from app.adapters.integrations.validation import safe_email, safe_header
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
_TIMEZONE = "UTC"
# Marks events this adapter created (parallels the seeder's marker) so a take's events are findable.
_CREATED_MARKER = "[change-court]"


class RealOutlookAdapter(BaseIntegrationAdapter):
    """Reads a user's Outlook calendar via Graph and performs contained calendar/draft writes."""

    def __init__(
        self, graph: GraphClient, calendar_upn: str, *, retry: RetryPolicy | None = None
    ) -> None:
        super().__init__(retry=retry)
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

    @staticmethod
    def _safe_day(value: str) -> str:
        """Re-validate the plan's ISO ``start`` at the boundary and return its date (YYYY-MM-DD).

        Intake already checks ``format:"date"``, but the adapter never trusts the parser's value.
        """
        try:
            datetime.fromisoformat(value.strip())
        except ValueError as exc:
            raise IntegrationError(f"{_SYSTEM}: invalid start date '{value}'") from exc
        return value.strip()[:10]

    def _event_payload(self, params: dict[str, object]) -> dict[str, object]:
        # The plan carries a date only; default to a 1-hour 09:00–10:00 UTC slot (timed, so it reads
        # back consistently with the seeded timed events and avoids the all-day Graph shape).
        day = self._safe_day(str(params["start"]))
        return {
            "subject": safe_header(str(params["title"]), field="title"),
            "start": {"dateTime": f"{day}T09:00:00", "timeZone": _TIMEZONE},
            "end": {"dateTime": f"{day}T10:00:00", "timeZone": _TIMEZONE},
            "body": {"contentType": "text", "content": _CREATED_MARKER},
        }

    def _draft_payload(self, params: dict[str, object]) -> dict[str, object]:
        # POST /messages lands in Drafts (isDraft true); this adapter never calls /send, and the app
        # is not granted Mail.Send — so the write surface is exercised without anything being sent.
        return {
            "subject": safe_header(str(params["subject"]), field="subject"),
            "body": {"contentType": "text", "content": str(params.get("body", ""))},
            "toRecipients": [{"emailAddress": {"address": safe_email(str(params["to"]))}}],
        }

    @staticmethod
    def _slim_event(ev: dict[str, object]) -> dict[str, object]:
        start = ev.get("start")
        return {
            "id": ev.get("id"),
            "subject": ev.get("subject"),
            "start": start.get("dateTime") if isinstance(start, dict) else None,
            "webLink": ev.get("webLink"),
        }

    @staticmethod
    def _slim_draft(msg: dict[str, object]) -> dict[str, object]:
        return {
            "id": msg.get("id"),
            "subject": msg.get("subject"),
            "isDraft": msg.get("isDraft", True),
            "sent": False,  # invariant: this adapter creates the draft and never sends it
            "webLink": msg.get("webLink"),
        }

    def _apply(self, step: ExecutionStep) -> dict[str, object]:
        name = step.capability.name
        if name == "outlook.create_event":
            created = self._graph.post_json(
                f"/users/{self._upn}/events", self._event_payload(step.params)
            )
            return {"created_event": self._slim_event(created)}
        if name == "outlook.draft_email":
            created = self._graph.post_json(
                f"/users/{self._upn}/messages", self._draft_payload(step.params)
            )
            return {"draft": self._slim_draft(created)}
        raise IntegrationError(f"{_SYSTEM}: unknown write capability '{name}'")

    def _fetch_before(self, step: ExecutionStep) -> dict[str, object]:
        return {}  # both writes are pure creates — there is no prior state to capture

    def _rollback(self, step: ExecutionStep, before: dict[str, object]) -> RollbackHint:
        if step.capability.name == "outlook.draft_email":
            instruction = "delete the created draft (it was never sent) to restore the prior state"
        else:
            instruction = "delete the created calendar event to restore the prior state"
        return RollbackHint(
            step_id=step.step_id, system=_SYSTEM, instruction=instruction, params=dict(step.params)
        )
