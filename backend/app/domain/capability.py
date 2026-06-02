"""Capability model: what an adapter can read or write, declared via its catalog."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.domain.enums import CapabilityKind


class Capability(BaseModel):
    """A single read or write capability an adapter registers.

    ``params_schema`` is a JSON Schema fragment used by the intake hallucination guard to validate
    the parameters of any action bound to this capability.
    """

    system: str
    name: str
    kind: CapabilityKind
    description: str = ""
    params_schema: dict[str, object] = Field(default_factory=dict)


class CapabilityRef(BaseModel):
    """Lightweight binding to a capability by ``(system, name)``."""

    system: str
    name: str
