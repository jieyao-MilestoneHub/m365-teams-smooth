"""Real SharePoint adapter over Microsoft Graph: reads folder evidence and grants scoped access.

Provides the *read* capabilities the trials rely on — listing a folder and detecting whether it
holds customer data (the decisive evidence behind the over-broad-scope refusal), and reading the
published change-freeze calendar (the release-freeze leg of the Reschedule breach evidence) — from
a configured SharePoint site's document libraries. The grant is contained: a LIVE
``grant_folder_permission`` issues a real least-privilege, time-boxed Microsoft Graph invite; under
DRY_RUN the base class predicts the effect instead. Selected when ``sharepoint`` runs in ``real``
mode with Graph credentials configured.
"""

from __future__ import annotations

import json

from app.adapters.integrations.base import BaseIntegrationAdapter
from app.adapters.integrations.graph import GraphClient
from app.adapters.integrations.retry import RetryPolicy
from app.adapters.integrations.validation import safe_email, safe_path
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
# A child folder by this name marks its parent as holding customer data.
_CUSTOMER_DATA_MARKER = "customerdata"
# The published change-freeze calendar: a JSON document ({"freezes": [{start, end, …}]}) in the
# demo library, seeded by scripts.seed_sharepoint from assets/sharepoint/.
_CHANGE_CALENDAR_PATH = "/ProjectX/change-freeze-calendar.json"
# Plan roles → Graph driveItem permission roles.
_ROLE_MAP = {"read": ["read"], "write": ["write"]}


class RealSharePointAdapter(BaseIntegrationAdapter):
    """Reads a configured site's document library via Graph and grants scoped folder access."""

    def __init__(
        self, graph: GraphClient, site_id: str, *, retry: RetryPolicy | None = None
    ) -> None:
        super().__init__(retry=retry)
        self._graph = graph
        self._site_id = site_id
        self._drive_ids: dict[str, str] = {}

    @property
    def system(self) -> str:
        return _SYSTEM

    def _capabilities(self) -> list[Capability]:
        return [
            Capability(system=_SYSTEM, name="sharepoint.read_folder", kind=CapabilityKind.READ),
            Capability(
                system=_SYSTEM, name="sharepoint.read_change_calendar", kind=CapabilityKind.READ
            ),
            Capability(
                system=_SYSTEM,
                name="sharepoint.grant_folder_permission",
                kind=CapabilityKind.WRITE,
                params_schema={
                    "required": ["path", "principal", "role"],
                    "properties": {
                        "role": {"pattern": "read|write"},
                        "expiry": {"format": "date"},
                    },
                },
            ),
        ]

    def _drive_id(self, library: str) -> str:
        # A SharePoint site has several document libraries (each a Graph "drive"); resolve by name.
        if not self._drive_ids:
            data = self._graph.get(
                f"/sites/{self._site_id}/drives", **{"$select": "id,name", "$top": "100"}
            )
            value = data.get("value", [])
            self._drive_ids = {
                str(d.get("name")): str(d.get("id"))
                for d in (value if isinstance(value, list) else [])
                if isinstance(d, dict)
            }
        drive_id = self._drive_ids.get(library)
        if not drive_id:
            raise IntegrationError(f"{_SYSTEM}: no document library named '{library}'")
        return drive_id

    def _children(self, path: str) -> list[dict[str, object]]:
        # The first path segment selects the document library; the rest is the in-library path,
        # addressed as the drive root or a subpath via the "root:/<path>:" form. Validate first so
        # a crafted path cannot traverse out of the scoped site.
        parts = [p for p in safe_path(path).strip("/").split("/") if p]
        if not parts:
            raise IntegrationError(
                f"{_SYSTEM}: path must name a document library, e.g. '/ProjectX'"
            )
        library, rest = parts[0], "/".join(parts[1:])
        segment = f"root:/{rest}:" if rest else "root"
        data = self._graph.get(
            f"/sites/{self._site_id}/drives/{self._drive_id(library)}/{segment}/children",
            **{"$select": "name,folder", "$top": "200"},
        )
        value = data.get("value", [])
        return list(value) if isinstance(value, list) else []

    def _read(self, query: ReadQuery) -> ReadResult:
        if query.capability == "sharepoint.read_folder":
            path = str(query.params.get("path", ""))
            names = [str(child.get("name", "")) for child in self._children(path)]
            contains_customer_data = (
                any(name.lower() == _CUSTOMER_DATA_MARKER for name in names)
                or path.strip("/").lower().endswith(_CUSTOMER_DATA_MARKER)
            )
            return ReadResult(
                capability=query.capability,
                data={
                    "path": path,
                    "items": names,
                    "contains_customer_data": contains_customer_data,
                },
            )
        if query.capability == "sharepoint.read_change_calendar":
            path = str(query.params.get("path", _CHANGE_CALENDAR_PATH))
            parts = [p for p in safe_path(path).strip("/").split("/") if p]
            if len(parts) < 2:
                raise IntegrationError(
                    f"{_SYSTEM}: change-calendar path must be '/<library>/<file>', got '{path}'"
                )
            library, rest = parts[0], "/".join(parts[1:])
            raw = self._graph.get_content(
                f"/sites/{self._site_id}/drives/{self._drive_id(library)}/root:/{rest}:/content"
            )
            calendar = json.loads(raw.decode("utf-8"))
            freezes = calendar.get("freezes") if isinstance(calendar, dict) else None
            return ReadResult(
                capability=query.capability,
                data={"freezes": freezes if isinstance(freezes, list) else []},
            )
        raise IntegrationError(f"{_SYSTEM}: unknown read capability '{query.capability}'")

    def _predict(self, step: ExecutionStep, before: dict[str, object]) -> PredictedEffect:
        return PredictedEffect(
            summary="would grant scoped folder permission", diff=dict(step.params)
        )

    def _resolve_item(self, path: str) -> tuple[str, str]:
        """Return ``(drive_id, driveItem_id)`` for a validated in-site path; raise on a bad path."""
        parts = [p for p in safe_path(path).strip("/").split("/") if p]
        if not parts:
            raise IntegrationError(
                f"{_SYSTEM}: path must name a document library, e.g. '/ProjectX'"
            )
        library, rest = parts[0], "/".join(parts[1:])
        drive_id = self._drive_id(library)
        segment = f"root:/{rest}:" if rest else "root"
        data = self._graph.get(
            f"/sites/{self._site_id}/drives/{drive_id}/{segment}", **{"$select": "id"}
        )
        item_id = str(data.get("id", ""))
        if not item_id:
            raise IntegrationError(f"{_SYSTEM}: folder '{path}' not found")
        return drive_id, item_id

    def _apply(self, step: ExecutionStep) -> dict[str, object]:
        if step.capability.name != "sharepoint.grant_folder_permission":
            raise IntegrationError(
                f"{_SYSTEM}: unknown write capability '{step.capability.name}'"
            )
        params = step.params
        principal = safe_email(str(params["principal"]))
        role = str(params["role"]).lower()
        roles = _ROLE_MAP.get(role)
        if roles is None:
            raise IntegrationError(f"{_SYSTEM}: unsupported role '{role}'")
        drive_id, item_id = self._resolve_item(str(params["path"]))
        body: dict[str, object] = {
            "recipients": [{"email": principal}],
            "roles": roles,
            "requireSignIn": True,
            "sendInvitation": False,
        }
        expiry = str(params.get("expiry", "")).strip()
        if expiry:
            # Plans carry a plain date; Graph wants an ISO-8601 timestamp. Best-effort on app-only
            # invites — the entra.schedule_access_revoke step is the authoritative time-box.
            body["expirationDateTime"] = expiry if len(expiry) > 10 else f"{expiry}T00:00:00Z"
        result = self._graph.post_json(
            f"/sites/{self._site_id}/drives/{drive_id}/items/{item_id}/invite", body
        )
        granted = result.get("value")
        perm = granted[0] if isinstance(granted, list) and granted else {}
        permission_id = str(perm.get("id", "")) if isinstance(perm, dict) else ""
        return {
            "grant": {
                "path": str(params["path"]),
                "principal": principal,
                "role": role,
                "expiry": expiry or None,
                "drive_id": drive_id,
                "item_id": item_id,
                "permission_id": permission_id,
            }
        }

    def _fetch_before(self, step: ExecutionStep) -> dict[str, object]:
        return {}  # a grant is additive — the new permission id is recorded in the after-state

    def _rollback(self, step: ExecutionStep, before: dict[str, object]) -> RollbackHint:
        return RollbackHint(
            step_id=step.step_id,
            system=_SYSTEM,
            instruction=(
                "revoke the granted folder permission — DELETE "
                "/drives/{drive_id}/items/{item_id}/permissions/{permission_id} using the ids "
                "recorded in the step's after-state"
            ),
            params=dict(step.params),
        )
