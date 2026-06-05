"""param_violations: required keys guard presence, pattern/format guard value shape."""

from __future__ import annotations

from app.domain import Capability, CapabilityKind, param_violations


def _cap(schema: dict[str, object]) -> Capability:
    return Capability(
        system="github",
        name="github.comment_issue",
        kind=CapabilityKind.WRITE,
        params_schema=schema,
    )


_SCHEMA: dict[str, object] = {
    "required": ["issue", "body"],
    "properties": {"issue": {"pattern": "^[0-9]+$"}},
}


def test_valid_params_pass() -> None:
    assert param_violations(_cap(_SCHEMA), {"issue": "42", "body": "x"}) == []


def test_int_value_passes_an_int_like_pattern() -> None:
    # Plans carry ints as well as strings; the constraint checks the stringified value.
    assert param_violations(_cap(_SCHEMA), {"issue": 42, "body": "x"}) == []


def test_missing_required_param_is_reported() -> None:
    violations = param_violations(_cap(_SCHEMA), {"issue": "42"})
    assert violations == ["missing required param 'body'"]


def test_pattern_violation_is_reported() -> None:
    # The live failure mode: a present-but-unusable value (issue #268).
    violations = param_violations(_cap(_SCHEMA), {"issue": "Milestone 'Launch'", "body": "x"})
    assert len(violations) == 1
    assert "must match" in violations[0]


def test_date_format_accepts_iso_date_and_datetime() -> None:
    schema: dict[str, object] = {"properties": {"due_on": {"format": "date"}}}
    assert param_violations(_cap(schema), {"due_on": "2026-06-17"}) == []
    assert param_violations(_cap(schema), {"due_on": "2026-06-17T00:00:00Z"}) == []


def test_date_format_rejects_non_iso_values() -> None:
    schema: dict[str, object] = {"properties": {"due_on": {"format": "date"}}}
    violations = param_violations(_cap(schema), {"due_on": "next Wednesday"})
    assert violations == ["param 'due_on' must be an ISO date, got 'next Wednesday'"]


def test_constraints_apply_only_to_present_params() -> None:
    # Optional constrained params are not required into existence by their constraint.
    schema: dict[str, object] = {"properties": {"issue": {"pattern": "^[0-9]+$"}}}
    assert param_violations(_cap(schema), {}) == []


def test_empty_schema_accepts_anything() -> None:
    assert param_violations(_cap({}), {"whatever": "goes"}) == []
