"""Post-execution verification: did each live write take effect as the reviewed plan asked?

Dry runs predict and never mutate, so there is nothing to verify; for a live step the requested
params are compared against the system's reported after-state on their shared keys. Verification
is advisory evidence for the audit record — it never blocks or reverses anything.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class EffectVerification(BaseModel):
    """One step's reflection: requested params vs the reported after-state."""

    step_id: str
    matched: bool = True
    checked: list[str] = Field(default_factory=list)  # param keys compared
    mismatches: list[str] = Field(default_factory=list)  # "key: expected X, got Y"


def verify_effect(
    step_id: str, params: dict[str, object], after: dict[str, object]
) -> EffectVerification:
    """Compare the step's requested params to the after-state on their shared keys."""
    checked: list[str] = []
    mismatches: list[str] = []
    for key, expected in params.items():
        if key not in after:
            continue  # the system did not report this field; nothing to compare
        checked.append(key)
        actual = after[key]
        if actual != expected:
            mismatches.append(f"{key}: expected {expected!r}, got {actual!r}")
    return EffectVerification(
        step_id=step_id, matched=not mismatches, checked=checked, mismatches=mismatches
    )
