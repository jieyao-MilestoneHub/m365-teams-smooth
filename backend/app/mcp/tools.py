"""MCP tools — thin façades over CourtService. No business logic lives here.

Tools are registered as closures capturing the service, so the server is built by dependency
injection (and unit-tested by calling the service directly or via ``FastMCP.call_tool``). Each tool
maps its string arguments to the domain enums and returns JSON-safe dicts.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from functools import wraps
from typing import ParamSpec

from mcp import McpError
from mcp.server.fastmcp import FastMCP
from mcp.types import ErrorData

from app.api.errors import classify, current_request_id, error_body, mcp_code
from app.domain import PlanKind, RunMode, VerdictType
from app.domain.errors import ChangeCourtError, NotFoundError
from app.mcp import correlate
from app.services.court_service import CourtService

logger = logging.getLogger(__name__)

P = ParamSpec("P")


def _translate_errors(fn: Callable[P, dict[str, object]]) -> Callable[P, dict[str, object]]:
    """Map a domain error raised in a tool to a structured MCP error, mirroring the REST surface.

    The typed mapping (``classify``) and the ``{error, detail, request_id}`` payload are shared with
    the HTTP handlers so both edges behave identically.
    """

    @wraps(fn)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> dict[str, object]:
        try:
            return fn(*args, **kwargs)
        except ChangeCourtError as exc:
            _, code = classify(exc)
            request_id = current_request_id()
            logger.warning("mcp tool error (%s): %s", code, exc)
            raise McpError(
                ErrorData(
                    code=mcp_code(code),
                    message=f"{code}: {exc}",
                    data=error_body(code, str(exc), request_id),
                )
            ) from exc

    return wrapper


def register_tools(mcp: FastMCP, service: CourtService) -> None:
    """Register the court tools on the MCP server."""

    @mcp.tool()
    @correlate
    @_translate_errors
    def submit_change(
        raw_request: str, source: str = "mcp", run_mode: str = "dry_run"
    ) -> dict[str, object]:
        """Put a change on trial; returns the trial summary (status, risk, plan, verdicts)."""
        summary = service.submit_change(raw_request, source=source, run_mode=RunMode(run_mode))
        return summary.model_dump(mode="json")

    @mcp.tool()
    @correlate
    @_translate_errors
    def get_status(thread_id: str) -> dict[str, object]:
        """Return the current lifecycle status of a trial."""
        return {"thread_id": thread_id, "status": service.get_status(thread_id)}

    @mcp.tool()
    @correlate
    @_translate_errors
    def get_trial(thread_id: str) -> dict[str, object]:
        """Return the full trial record (change, impact, options, risk, quorum, verdict)."""
        trial = service.get_trial(thread_id)
        if trial is None:
            raise NotFoundError(f"unknown trial: {thread_id}")
        return trial.model_dump(mode="json")

    @mcp.tool()
    @correlate
    @_translate_errors
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
