"""The cast verdict that resumes the court from its interrupt."""

from __future__ import annotations

from pydantic import BaseModel

from app.domain.enums import PlanKind, VerdictType


class Verdict(BaseModel):
    """A reviewer's decision. ``selected_plan`` picks which plan ``execute`` runs.

    ``idempotency_key`` makes casting the same verdict twice a no-op across REST and MCP.
    """

    verdict_id: str
    type: VerdictType
    selected_plan: PlanKind = PlanKind.FEASIBLE
    actor: str = "unknown"
    note: str | None = None
    idempotency_key: str
