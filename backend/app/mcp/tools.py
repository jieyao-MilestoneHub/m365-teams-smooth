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
from app.domain.errors import ChangeCourtError, NotFoundError, UnauthorizedApproverError
from app.domain.principal import Principal
from app.mcp import correlate
from app.mcp.security import current_principal
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


def _require_principal() -> Principal:
    """The authenticated caller, required for approval actions (no anonymous approvals)."""
    actor = current_principal()
    if actor is None:
        raise UnauthorizedApproverError("authentication is required for approval actions")
    return actor


def register_tools(mcp: FastMCP, service: CourtService) -> None:
    """Register the court tools on the MCP server."""

    @mcp.tool()
    @correlate
    @_translate_errors
    def submit_change(
        raw_request: str, source: str = "mcp", run_mode: str = "dry_run"
    ) -> dict[str, object]:
        """Put a change on trial; returns the trial summary (status, risk, plan, verdicts).

        ``run_mode`` is ``"dry_run"`` (predict effects, no side effects), ``"live"`` (apply), or
        ``"analyze"`` — an impact check only: the trial returns its evidence, risk, plan, and
        would-be approvers with status ``analyzed`` and never executes; use ``get_trial`` for the
        full record (the approvers are under ``quorum.required_approvers``).
        """
        summary = service.submit_change(
            raw_request,
            source=source,
            run_mode=RunMode(run_mode),
            requester=_require_principal(),
        )
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
        """Return the full trial record (change, impact, options, risk, quorum, verdict, and the
        per-node reasoning trace under ``deliberation``)."""
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
        """Cast a verdict and resume the trial. Idempotent per (thread_id, idempotency_key).

        The result keeps the two outcomes separate: ``verdict_recorded`` confirms the verdict was
        persisted, and ``execution_status`` reports the resumed run (``done``, ``failed``, …).
        ``execution_status: "failed"`` means one or more plan steps failed *after* a successfully
        recorded verdict — explain it as a partial execution failure (see the audit record), never
        as a failed approval, and do not ask the caller to cast again.
        """
        # Authorization keys off the authenticated caller, never the spoofable `actor` label —
        # the service enforces the same separation of duties as decide on every verdict.
        result = service.cast_verdict(
            thread_id,
            VerdictType(verdict_type),
            selected_plan=PlanKind(selected_plan),
            idempotency_key=idempotency_key,
            actor=actor,
            principal=_require_principal(),
        )
        return result.model_dump(mode="json")

    @mcp.tool()
    @correlate
    @_translate_errors
    def send_for_approval(thread_id: str, note: str) -> dict[str, object]:
        """Requester gate: send the trial to its approvers with a mandatory note."""
        summary = service.send_for_approval(thread_id, actor=_require_principal(), note=note)
        return summary.model_dump(mode="json")

    @mcp.tool()
    @correlate
    @_translate_errors
    def withdraw_change(thread_id: str) -> dict[str, object]:
        """Requester gate: give up the change instead of sending it for approval."""
        summary = service.withdraw_change(thread_id, actor=_require_principal())
        return summary.model_dump(mode="json")

    @mcp.tool()
    @correlate
    @_translate_errors
    def decide(thread_id: str, approve: bool, note: str = "") -> dict[str, object]:
        """Approver gate: approve, or reject with a note. The requester cannot self-approve."""
        summary = service.decide(
            thread_id, actor=_require_principal(), approve=approve, note=note
        )
        return summary.model_dump(mode="json")

    @mcp.tool()
    @correlate
    @_translate_errors
    def list_pending_approvals() -> dict[str, object]:
        """Trials awaiting the caller's approval (authorized role, not their own requests)."""
        summaries = service.list_pending_approvals(_require_principal())
        return {"pending": [summary.model_dump(mode="json") for summary in summaries]}

    @mcp.tool()
    @correlate
    @_translate_errors
    def acknowledge_outcome(thread_id: str) -> dict[str, object]:
        """Requester gate: confirm the concluded outcome so all parties are demonstrably synced."""
        summary = service.acknowledge(thread_id, actor=_require_principal())
        return summary.model_dump(mode="json")
