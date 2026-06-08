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


def _comparable(value: object) -> bool:
    """Only scalars are verified. A structured after-state (e.g. the full milestone object the API
    returns under the same key as the request's title param) is the record's representation, not a
    scalar to check a requested value against."""
    return not isinstance(value, (dict, list))


def _normalize(value: object) -> str:
    """Canonical string form, so values equal in meaning but not representation still match:
    ``7`` vs ``"7"`` (type), and ``"2026-06-17T00:00:00Z"`` vs ``"2026-06-17"`` (date precision)."""
    text = str(value).strip()
    # Plan params carry plain dates; collapse an ISO datetime to its date so the two compare equal.
    if "T" in text and len(text) >= 10 and text[4:5] == "-" and text[7:8] == "-":
        return text[:10]
    return text


def verify_effect(
    step_id: str, params: dict[str, object], after: dict[str, object]
) -> EffectVerification:
    """Compare the step's requested params to the after-state on their shared, comparable keys."""
    checked: list[str] = []
    mismatches: list[str] = []
    for key, expected in params.items():
        if key not in after:
            continue  # the system did not report this field; nothing to compare
        actual = after[key]
        if not _comparable(actual):
            continue  # a structured object, not a scalar value to verify against — skip
        checked.append(key)
        if _normalize(actual) != _normalize(expected):
            mismatches.append(f"{key}: expected {expected!r}, got {actual!r}")
    return EffectVerification(
        step_id=step_id, matched=not mismatches, checked=checked, mismatches=mismatches
    )
