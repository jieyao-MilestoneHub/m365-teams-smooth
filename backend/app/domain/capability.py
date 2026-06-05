"""Capability model: what an adapter can read or write, declared via its catalog."""

from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, Field

from app.domain.enums import CapabilityKind


class Capability(BaseModel):
    """A single read or write capability an adapter registers.

    ``params_schema`` is a JSON Schema fragment used by the intake hallucination guard and the
    planners to validate the parameters of any action bound to this capability. Beyond
    ``required`` (key presence), a per-property ``pattern`` (full-match regex) and
    ``format: "date"`` (ISO 8601 date or datetime) constrain the *value* — see
    :func:`param_violations` for the supported subset.
    """

    system: str
    name: str
    kind: CapabilityKind
    description: str = ""
    params_schema: dict[str, object] = Field(default_factory=dict)


def param_violations(capability: Capability, params: dict[str, object]) -> list[str]:
    """Check ``params`` against the capability's schema; return human-readable violations.

    Enforces the minimal subset the catalogs declare — ``required`` keys must be present, and a
    present value must satisfy its property's ``pattern`` (regex full-match on the stringified
    value) and ``format: "date"`` (ISO 8601 date or datetime, trailing ``Z`` accepted). A required
    param guards *presence*; these constraints guard *shape*, so an underspecified-but-present
    value (e.g. a non-numeric issue reference) is blocked at planning instead of failing the call
    at execution.
    """
    schema = capability.params_schema or {}
    violations: list[str] = []

    required = schema.get("required", [])
    if isinstance(required, list):
        violations.extend(f"missing required param '{k}'" for k in required if k not in params)

    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        return violations
    for key, constraint in properties.items():
        if key not in params or not isinstance(constraint, dict):
            continue
        value = str(params[key])
        pattern = constraint.get("pattern")
        if isinstance(pattern, str) and re.fullmatch(pattern, value) is None:
            violations.append(f"param '{key}' must match {pattern}, got '{value}'")
        if constraint.get("format") == "date" and not _is_iso_date(value):
            violations.append(f"param '{key}' must be an ISO date, got '{value}'")
    return violations


def _is_iso_date(value: str) -> bool:
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


class CapabilityRef(BaseModel):
    """Lightweight binding to a capability by ``(system, name)``."""

    system: str
    name: str
