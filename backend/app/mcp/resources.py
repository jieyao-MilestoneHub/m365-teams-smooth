"""MCP resources — read-only views over the court, as façades over CourtService.

Exposes the full trial, an append-only audit record, and the capability catalog under ``court://``
URIs. Returns JSON strings so the content type is unambiguous.
"""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from app.mcp import correlate
from app.observability import metrics
from app.services.court_service import CourtService


def register_resources(mcp: FastMCP, service: CourtService) -> None:
    """Register the court resources on the MCP server."""

    @mcp.resource("court://trial/{thread_id}")
    @correlate
    def trial(thread_id: str) -> str:
        """The full trial record for a thread."""
        record = service.get_trial(thread_id)
        return json.dumps(record.model_dump(mode="json") if record is not None else None)

    @mcp.resource("court://audit/{audit_id}")
    @correlate
    def audit(audit_id: str) -> str:
        """The append-only audit record for an executed trial."""
        record = service.get_audit(audit_id)
        if record is None:
            return json.dumps(None)
        # before_after / rollback_hints are derived views (not stored fields), so the resource
        # adds them explicitly to keep the published payload shape unchanged.
        payload = record.model_dump(mode="json")
        payload["before_after"] = [b.model_dump(mode="json") for b in record.before_after]
        payload["rollback_hints"] = [r.model_dump(mode="json") for r in record.rollback_hints]
        return json.dumps(payload)

    @mcp.resource("court://capabilities")
    @correlate
    def capabilities() -> str:
        """The merged read + write capability catalog the court can act on."""
        return json.dumps([c.model_dump(mode="json") for c in service.capabilities()])

    @mcp.resource("court://metrics")
    @correlate
    def court_metrics() -> str:
        """At-a-glance counters and timers; ``enabled: false`` when metrics are turned off."""
        return json.dumps(metrics.snapshot())
