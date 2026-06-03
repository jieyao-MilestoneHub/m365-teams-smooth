"""Real SharePoint adapter (read-only evidence path) over Microsoft Graph.

Provides the *read* capability the Vendor Access trial relies on — listing a folder and detecting
whether it holds customer data (the decisive evidence behind the over-broad-scope refusal) — from a
configured SharePoint site's default document library. The grant (write) is intentionally NOT
performed: under DRY_RUN the base class predicts the effect, and a LIVE write is refused and
contained. Selected when ``sharepoint`` runs in ``real`` mode with Graph credentials configured.
"""

from __future__ import annotations

from app.adapters.integrations.base import BaseIntegrationAdapter
from app.adapters.integrations.graph import GraphClient
from app.adapters.integrations.retry import RetryPolicy
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


class RealSharePointAdapter(BaseIntegrationAdapter):
    """Reads a configured site's document library via Graph; the grant stays dry-run only."""

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
                system=_SYSTEM,
                name="sharepoint.grant_folder_permission",
                kind=CapabilityKind.WRITE,
                params_schema={"required": ["path", "principal", "role"]},
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
        # addressed as the drive root or a subpath via the "root:/<path>:" form.
        parts = [p for p in path.strip("/").split("/") if p]
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
        raise IntegrationError(f"{_SYSTEM}: unknown read capability '{query.capability}'")

    def _predict(self, step: ExecutionStep, before: dict[str, object]) -> PredictedEffect:
        return PredictedEffect(
            summary="would grant scoped folder permission", diff=dict(step.params)
        )

    def _apply(self, step: ExecutionStep) -> dict[str, object]:
        # Read-only evidence adapter: real writes are out of scope; execution runs in DRY_RUN.
        raise IntegrationError(f"{_SYSTEM}: real writes are disabled (dry-run only)")

    def _fetch_before(self, step: ExecutionStep) -> dict[str, object]:
        return {}

    def _rollback(self, step: ExecutionStep, before: dict[str, object]) -> RollbackHint:
        return RollbackHint(
            step_id=step.step_id,
            system=_SYSTEM,
            instruction="revoke the granted folder permission",
            params=dict(step.params),
        )
