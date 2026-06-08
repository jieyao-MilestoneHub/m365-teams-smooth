"""Service-layer DTOs returned to the façades (REST/MCP). Boundary types, not domain models."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.domain import RunEvent, TrialRecord


class TrialSummary(BaseModel):
    """A compact view of a trial for the Change Court card and status queries."""

    thread_id: str
    change_id: str
    status: str
    risk_level: str | None = None
    requires_approval: bool = False
    unsafe: bool = False
    plan_kind: str | None = None
    verdict_options: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    acknowledged: bool = False  # requester confirmed the concluded outcome
    run_url: str | None = None  # signed read-only run-page link; None when the run page is disabled


class ApprovalTimelineEntry(BaseModel):
    """One approval action rendered for the run view (derived from the approval ledger)."""

    decision: str
    actor: str  # display label, not a delivery address
    role: str | None = None
    note: str = ""
    at: str = ""


class RunView(BaseModel):
    """Everything a run-page poll needs: progress events, approval timeline, and trial detail.

    ``events`` carries only events with ``seq > after_seq`` so a poller advances incrementally
    via ``last_seq``; ``trial`` is the full current record (refreshed every poll) for the stage
    detail panes.
    """

    summary: TrialSummary
    trial: TrialRecord | None = None
    events: list[RunEvent] = Field(default_factory=list)
    approvals: list[ApprovalTimelineEntry] = Field(default_factory=list)
    last_seq: int = 0
    run_mode: str | None = None
    audit_id: str | None = None


class CastResult(BaseModel):
    """The outcome of casting a verdict.

    Verdict persistence and run outcome are separate facts: ``verdict_recorded`` says the verdict
    itself was persisted (a failing plan step never undoes it), while ``execution_status`` carries
    the resumed run's lifecycle status (``done``, ``failed``, …). A failed execution therefore
    never means a failed approval — re-casting is idempotent but pointless.
    """

    thread_id: str
    verdict_recorded: bool = True
    execution_status: str
    audit_id: str | None = None
    idempotent: bool = False
    run_url: str | None = None  # signed read-only run-page link; None when the run page is disabled
