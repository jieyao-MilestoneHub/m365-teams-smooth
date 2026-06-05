"""BaseIntegrationAdapter enforces the dry-run guarantee and contains errors; registry selects."""

from __future__ import annotations

import pytest

from app.adapters.integrations.base import BaseIntegrationAdapter
from app.adapters.integrations.registry import build_registry
from app.config import Settings
from app.domain import (
    Capability,
    CapabilityKind,
    CapabilityRef,
    ExecutionStep,
    PredictedEffect,
    RequestedAction,
    RollbackHint,
    RunMode,
    StepStatus,
)
from app.domain.errors import CapabilityNotFoundError
from app.ports.integration import ReadQuery, ReadResult


class _ProbeAdapter(BaseIntegrationAdapter):
    """Records whether the real-mutation hook ran, and can be told to fail on apply."""

    def __init__(
        self,
        *,
        system: str = "probe",
        fail_apply: bool = False,
        value_pattern: str | None = None,
    ) -> None:
        self._system = system
        self._fail_apply = fail_apply
        self._value_pattern = value_pattern
        self.applied = False
        self.store: dict[str, object] = {"value": 1}

    @property
    def system(self) -> str:
        return self._system

    def _capabilities(self) -> list[Capability]:
        schema: dict[str, object] = {"required": ["value"]}
        if self._value_pattern:
            schema["properties"] = {"value": {"pattern": self._value_pattern}}
        return [
            Capability(
                system=self._system,
                name=f"{self._system}.set_value",
                kind=CapabilityKind.WRITE,
                params_schema=schema,
            )
        ]

    def _read(self, query: ReadQuery) -> ReadResult:
        return ReadResult(capability=query.capability, data=dict(self.store))

    def _predict(self, step: ExecutionStep, before: dict[str, object]) -> PredictedEffect:
        return PredictedEffect(summary="would set value", diff={"value": step.params.get("value")})

    def _apply(self, step: ExecutionStep) -> dict[str, object]:
        if self._fail_apply:
            raise RuntimeError("backend exploded")
        self.applied = True
        self.store["value"] = step.params["value"]
        return dict(self.store)

    def _fetch_before(self, step: ExecutionStep) -> dict[str, object]:
        return dict(self.store)

    def _rollback(self, step: ExecutionStep, before: dict[str, object]) -> RollbackHint:
        return RollbackHint(
            step_id=step.step_id, system=self._system, instruction="restore", params=before
        )


def _step() -> ExecutionStep:
    return ExecutionStep(
        step_id="s1",
        capability=CapabilityRef(system="probe", name="probe.set_value"),
        params={"value": 42},
    )


def test_dry_run_predicts_without_mutating() -> None:
    adapter = _ProbeAdapter()
    result = adapter.execute(_step(), RunMode.DRY_RUN)
    assert result.status is StepStatus.DRY_RUN
    assert result.predicted is not None
    assert adapter.applied is False  # _apply never ran
    assert adapter.store["value"] == 1  # store untouched
    assert result.rollback is not None


def test_live_applies_and_snapshots() -> None:
    adapter = _ProbeAdapter()
    result = adapter.execute(_step(), RunMode.LIVE)
    assert result.status is StepStatus.OK
    assert adapter.applied is True
    assert result.after == {"value": 42}


def test_apply_failure_is_contained_as_failed_result() -> None:
    adapter = _ProbeAdapter(fail_apply=True)
    result = adapter.execute(_step(), RunMode.LIVE)  # must not raise
    assert result.status is StepStatus.FAILED
    assert result.error is not None and "probe" in result.error
    assert result.rollback is not None  # rollback hint still offered


def test_validate_rejects_unknown_and_missing_params() -> None:
    adapter = _ProbeAdapter()
    with pytest.raises(CapabilityNotFoundError):
        adapter.validate(RequestedAction(system="probe", capability_name="probe.delete_everything"))
    with pytest.raises(CapabilityNotFoundError):
        adapter.validate(
            RequestedAction(system="probe", capability_name="probe.set_value", params={})
        )
    adapter.validate(
        RequestedAction(system="probe", capability_name="probe.set_value", params={"value": 1})
    )


def test_validate_rejects_malformed_param_values() -> None:
    # The schema's value constraints are enforced at validate, not discovered at execution.
    adapter = _ProbeAdapter(value_pattern="^[0-9]+$")
    with pytest.raises(CapabilityNotFoundError):
        adapter.validate(
            RequestedAction(
                system="probe", capability_name="probe.set_value", params={"value": "not-a-number"}
            )
        )
    adapter.validate(
        RequestedAction(system="probe", capability_name="probe.set_value", params={"value": 7})
    )


def test_registry_selects_mock_under_force_all_mock() -> None:
    real = _ProbeAdapter(system="github")
    mock = _ProbeAdapter(system="github")
    settings = Settings(integration_mode="github:real", force_all_mock=True)
    registry = build_registry(settings, {"github": {"real": real, "mock": mock}})
    assert registry.get("github") is mock
    assert any(c.name == "github.set_value" for c in registry.capabilities())
