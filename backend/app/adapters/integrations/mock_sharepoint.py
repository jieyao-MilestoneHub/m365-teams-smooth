"""Mock SharePoint adapter: read a folder (incl. whether it holds customer data) and grant access.

Grants carry a role and an expiry, so the Vendor Access trial can propose least-privilege,
time-boxed access (read-only to one folder until a fixed date) instead of broad standing access.
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

_SYSTEM = "sharepoint"

# Seeded folders. LaunchAssets is safe to share read-only; the CustomerData folder is not.
_FOLDERS: dict[str, dict[str, object]] = {
    "/ProjectX/LaunchAssets": {
        "items": ["brief.docx", "timeline.xlsx"],
        "contains_customer_data": False,
    },
    "/ProjectX": {
        "items": ["LaunchAssets", "CustomerData"],
        "contains_customer_data": True,
    },
    "/ProjectX/CustomerData": {
        "items": ["accounts.csv"],
        "contains_customer_data": True,
    },
}


class MockSharePointAdapter(BaseIntegrationAdapter):
    """In-memory SharePoint stand-in."""

    def __init__(self) -> None:
        self._grants: list[dict[str, object]] = []

    @property
    def system(self) -> str:
        return _SYSTEM

    def _capabilities(self) -> list[Capability]:
        return [
            Capability(system=_SYSTEM, name="sharepoint.read_folder", kind=CapabilityKind.READ),
            Capability(
                system=_SYSTEM,
                name="sharepoint.grant_folder_permission",
                kind=CapabilityKind.WRITE,
                params_schema={"required": ["path", "principal", "role"]},
            ),
        ]

    def _read(self, query: ReadQuery) -> ReadResult:
        if query.capability == "sharepoint.read_folder":
            path = str(query.params.get("path", ""))
            folder = _FOLDERS.get(path, {"items": [], "contains_customer_data": False})
            return ReadResult(capability=query.capability, data={"path": path, **folder})
        raise IntegrationError(f"{_SYSTEM}: unknown read capability '{query.capability}'")

    def _predict(self, step: ExecutionStep, before: dict[str, object]) -> PredictedEffect:
        return PredictedEffect(
            summary="would grant scoped folder permission",
            diff=dict(step.params),
        )

    def _apply(self, step: ExecutionStep) -> dict[str, object]:
        grant = dict(step.params)
        self._grants.append(grant)
        return {"grant": grant}

    def _fetch_before(self, step: ExecutionStep) -> dict[str, object]:
        return {"grants": len(self._grants)}

    def _rollback(self, step: ExecutionStep, before: dict[str, object]) -> RollbackHint:
        return RollbackHint(
            step_id=step.step_id,
            system=_SYSTEM,
            instruction="revoke the granted folder permission",
            params=dict(step.params),
        )
