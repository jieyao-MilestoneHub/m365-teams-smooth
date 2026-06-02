"""Mock Entra adapter: invite an external guest and schedule an automatic access revoke.

Write-only. The scheduled revoke is what makes Vendor Access time-boxed: access is granted with an
explicit expiry and an auto-revoke task, never as standing access.
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

_SYSTEM = "entra"


class MockEntraAdapter(BaseIntegrationAdapter):
    """In-memory Entra stand-in."""

    def __init__(self) -> None:
        self._guests: list[dict[str, object]] = []
        self._revokes: list[dict[str, object]] = []

    @property
    def system(self) -> str:
        return _SYSTEM

    def _capabilities(self) -> list[Capability]:
        return [
            Capability(
                system=_SYSTEM,
                name="entra.invite_guest",
                kind=CapabilityKind.WRITE,
                params_schema={"required": ["email"]},
            ),
            Capability(
                system=_SYSTEM,
                name="entra.schedule_access_revoke",
                kind=CapabilityKind.WRITE,
                params_schema={"required": ["principal", "revoke_on"]},
            ),
        ]

    def _read(self, query: ReadQuery) -> ReadResult:
        raise IntegrationError(f"{_SYSTEM}: no read capabilities")

    def _predict(self, step: ExecutionStep, before: dict[str, object]) -> PredictedEffect:
        if step.capability.name == "entra.invite_guest":
            return PredictedEffect(summary="would invite an external guest", diff=dict(step.params))
        return PredictedEffect(summary="would schedule an auto-revoke", diff=dict(step.params))

    def _apply(self, step: ExecutionStep) -> dict[str, object]:
        if step.capability.name == "entra.invite_guest":
            guest = {**step.params, "status": "invited"}
            self._guests.append(guest)
            return {"guest": guest}
        if step.capability.name == "entra.schedule_access_revoke":
            task = {**step.params, "status": "scheduled"}
            self._revokes.append(task)
            return {"revoke_task": task}
        raise IntegrationError(f"{_SYSTEM}: unknown write capability '{step.capability.name}'")

    def _fetch_before(self, step: ExecutionStep) -> dict[str, object]:
        if step.capability.name == "entra.invite_guest":
            return {"guests": len(self._guests)}
        return {"revokes": len(self._revokes)}

    def _rollback(self, step: ExecutionStep, before: dict[str, object]) -> RollbackHint:
        return RollbackHint(
            step_id=step.step_id,
            system=_SYSTEM,
            instruction="cancel the guest invite / scheduled revoke",
            params=dict(step.params),
        )
