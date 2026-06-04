"""The structured change and its requested actions, produced by the intake node."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.domain.enums import ChangeStatus
from app.domain.principal import Principal


class RequestedAction(BaseModel):
    """One intended action parsed from the request, bound to a catalog capability."""

    system: str
    capability_name: str
    verb: str = ""
    params: dict[str, object] = Field(default_factory=dict)


class Change(BaseModel):
    """The structured form of a request under trial."""

    change_id: str
    raw_request: str
    source: str = "unknown"
    requester: Principal | None = None  # authenticated opener (separation of duties)
    subject: str | None = None
    due_by: str | None = None
    requested_actions: list[RequestedAction] = Field(default_factory=list)
    status: ChangeStatus = ChangeStatus.INTAKE
    unsafe: bool = False
    unsafe_reason: str | None = None
