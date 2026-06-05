"""Service-layer DTOs returned to the façades (REST/MCP). Boundary types, not domain models."""

from __future__ import annotations

from pydantic import BaseModel, Field


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
