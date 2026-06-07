"""Mock Teams adapter: announcements, escalation threads, and meeting discussion notes.

The seeded announcement references the original launch date, so a reschedule surfaces a pending
communication that must be updated; the seeded standup notes carry the spoken follow-ups the
meeting-actions trial turns into tracked tasks.
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

_SYSTEM = "teams"


class MockTeamsAdapter(BaseIntegrationAdapter):
    """In-memory Teams stand-in."""

    def __init__(self) -> None:
        self._announcements: dict[str, str] = {
            "launch": "Launch is scheduled for 2026-06-10.",
        }
        self._threads: list[dict[str, object]] = []
        self._posts: list[dict[str, object]] = []
        # Spoken follow-ups from the last standup — the raw material for tracked action items.
        self._meeting_notes: dict[str, list[dict[str, str]]] = {
            "standup": [
                {"author": "Alex", "text": "I'll finish the API spec by 2026-06-12."},
                {"author": "Jamie", "text": "Design sign-off needs confirming by 2026-06-13."},
                {"author": "PM", "text": "The launch doc must be updated by 2026-06-14."},
                {"author": "Sam", "text": "Let's review progress together next week."},
            ],
        }

    @property
    def system(self) -> str:
        return _SYSTEM

    def _capabilities(self) -> list[Capability]:
        return [
            Capability(system=_SYSTEM, name="teams.read_announcement", kind=CapabilityKind.READ),
            Capability(system=_SYSTEM, name="teams.read_meeting_notes", kind=CapabilityKind.READ),
            Capability(
                system=_SYSTEM,
                name="teams.update_announcement",
                kind=CapabilityKind.WRITE,
                params_schema={"required": ["channel", "message"]},
            ),
            Capability(
                system=_SYSTEM,
                name="teams.create_escalation_thread",
                kind=CapabilityKind.WRITE,
                params_schema={"required": ["channel", "title"]},
            ),
            Capability(
                system=_SYSTEM,
                name="teams.post_message",
                kind=CapabilityKind.WRITE,
                params_schema={"required": ["channel", "message"]},
            ),
        ]

    def _read(self, query: ReadQuery) -> ReadResult:
        if query.capability == "teams.read_announcement":
            channel = str(query.params.get("channel", "launch"))
            message = self._announcements.get(channel, "")
            return ReadResult(
                capability=query.capability,
                data={"channel": channel, "message": message, "exists": bool(message)},
            )
        if query.capability == "teams.read_meeting_notes":
            channel = str(query.params.get("channel", "standup"))
            notes = self._meeting_notes.get(channel, [])
            return ReadResult(
                capability=query.capability,
                data={"channel": channel, "notes": [dict(n) for n in notes]},
            )
        raise IntegrationError(f"{_SYSTEM}: unknown read capability '{query.capability}'")

    def _predict(self, step: ExecutionStep, before: dict[str, object]) -> PredictedEffect:
        if step.capability.name == "teams.update_announcement":
            return PredictedEffect(
                summary="would update the channel announcement", diff=dict(step.params)
            )
        if step.capability.name == "teams.post_message":
            return PredictedEffect(
                summary="would post a message to the channel", diff=dict(step.params)
            )
        return PredictedEffect(summary="would open an escalation thread", diff=dict(step.params))

    def _apply(self, step: ExecutionStep) -> dict[str, object]:
        if step.capability.name == "teams.update_announcement":
            channel = str(step.params["channel"])
            self._announcements[channel] = str(step.params["message"])
            return {"channel": channel, "message": self._announcements[channel]}
        if step.capability.name == "teams.create_escalation_thread":
            thread = dict(step.params)
            self._threads.append(thread)
            return {"thread": thread}
        if step.capability.name == "teams.post_message":
            post = dict(step.params)
            self._posts.append(post)
            return {"post": post}
        raise IntegrationError(f"{_SYSTEM}: unknown write capability '{step.capability.name}'")

    def _fetch_before(self, step: ExecutionStep) -> dict[str, object]:
        if step.capability.name == "teams.update_announcement":
            channel = str(step.params.get("channel", "launch"))
            return {"channel": channel, "message": self._announcements.get(channel, "")}
        if step.capability.name == "teams.post_message":
            return {"posts": len(self._posts)}
        return {"threads": len(self._threads)}

    def _rollback(self, step: ExecutionStep, before: dict[str, object]) -> RollbackHint:
        return RollbackHint(
            step_id=step.step_id,
            system=_SYSTEM,
            instruction="restore the prior announcement / delete the escalation thread or post",
            params=before,
        )
