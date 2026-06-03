"""MCP tools — thin façades over CourtService. No business logic lives here.

Tools are registered as closures capturing the service, so the server is built by dependency
injection (and unit-tested by calling the service directly or via ``FastMCP.call_tool``). Each tool
maps its string arguments to the domain enums and returns JSON-safe dicts.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from app.domain import PlanKind, RunMode, VerdictType
from app.mcp import correlate
from app.services.court_service import CourtService


def register_tools(mcp: FastMCP, service: CourtService) -> None:
    """Register the court tools on the MCP server."""

    @mcp.tool()
    @correlate
    def submit_change(
        raw_request: str, source: str = "mcp", run_mode: str = "dry_run"
    ) -> dict[str, object]:
        """Put a change on trial; returns the trial summary (status, risk, plan, verdicts)."""
        summary = service.submit_change(raw_request, source=source, run_mode=RunMode(run_mode))
        return summary.model_dump(mode="json")

    @mcp.tool()
    @correlate
    def get_status(thread_id: str) -> dict[str, object]:
        """Return the current lifecycle status of a trial."""
        return {"thread_id": thread_id, "status": service.get_status(thread_id)}

    @mcp.tool()
    @correlate
    def get_trial(thread_id: str) -> dict[str, object]:
        """Return the full trial record (change, impact, options, risk, quorum, verdict)."""
        trial = service.get_trial(thread_id)
        if trial is None:
            raise ValueError(f"unknown trial: {thread_id}")
        return trial.model_dump(mode="json")

    @mcp.tool()
    @correlate
    def cast_verdict(
        thread_id: str,
        verdict_type: str,
        selected_plan: str = "feasible",
        idempotency_key: str | None = None,
        actor: str = "reviewer",
    ) -> dict[str, object]:
        """Cast a verdict and resume the trial. Idempotent per (thread_id, idempotency_key)."""
        result = service.cast_verdict(
            thread_id,
            VerdictType(verdict_type),
            selected_plan=PlanKind(selected_plan),
            idempotency_key=idempotency_key,
            actor=actor,
        )
        return result.model_dump(mode="json")
