"""Mock Teams adapter: read/update a channel announcement and open an escalation thread.

The seeded announcement references the original launch date, so the Launch Slip trial surfaces a
pending communication that must be updated; the escalation thread backs the Customer Promise flow.
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

    @property
    def system(self) -> str:
        return _SYSTEM

    def _capabilities(self) -> list[Capability]:
        return [
            Capability(system=_SYSTEM, name="teams.read_announcement", kind=CapabilityKind.READ),
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
        ]

    def _read(self, query: ReadQuery) -> ReadResult:
        if query.capability == "teams.read_announcement":
            channel = str(query.params.get("channel", "launch"))
            message = self._announcements.get(channel, "")
            return ReadResult(
                capability=query.capability,
                data={"channel": channel, "message": message, "exists": bool(message)},
            )
        raise IntegrationError(f"{_SYSTEM}: unknown read capability '{query.capability}'")

    def _predict(self, step: ExecutionStep, before: dict[str, object]) -> PredictedEffect:
        if step.capability.name == "teams.update_announcement":
            return PredictedEffect(
                summary="would update the channel announcement", diff=dict(step.params)
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
        raise IntegrationError(f"{_SYSTEM}: unknown write capability '{step.capability.name}'")

    def _fetch_before(self, step: ExecutionStep) -> dict[str, object]:
        if step.capability.name == "teams.update_announcement":
            channel = str(step.params.get("channel", "launch"))
            return {"channel": channel, "message": self._announcements.get(channel, "")}
        return {"threads": len(self._threads)}

    def _rollback(self, step: ExecutionStep, before: dict[str, object]) -> RollbackHint:
        return RollbackHint(
            step_id=step.step_id,
            system=_SYSTEM,
            instruction="restore the prior announcement / delete the escalation thread",
            params=before,
        )
