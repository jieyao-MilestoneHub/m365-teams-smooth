"""The IntegrationAdapter port enforces its contract: ABCs can't be instantiated bare."""

from __future__ import annotations

import pytest

from app.domain import (
    Capability,
    CapabilityKind,
    CapabilityRef,
    ExecutionStep,
    RequestedAction,
    RollbackHint,
    RunMode,
    StepResult,
    StepStatus,
)
from app.ports.integration import IntegrationAdapter, ReadQuery, ReadResult


class _FakeAdapter(IntegrationAdapter):
    """Minimal concrete adapter used only to exercise the port surface."""

    @property
    def system(self) -> str:
        return "fake"

    def capabilities(self) -> list[Capability]:
        return [Capability(system="fake", name="fake.read_thing", kind=CapabilityKind.READ)]

    def validate(self, action: RequestedAction) -> None:
        return None

    def read(self, query: ReadQuery) -> ReadResult:
        return ReadResult(capability=query.capability, data={"ok": True})

    def execute(self, step: ExecutionStep, mode: RunMode) -> StepResult:
        status = StepStatus.DRY_RUN if mode is RunMode.DRY_RUN else StepStatus.OK
        return StepResult(step_id=step.step_id, status=status)

    def fetch_before(self, step: ExecutionStep) -> dict[str, object]:
        return {}

    def suggest_rollback(self, step: ExecutionStep, before: dict[str, object]) -> RollbackHint:
        return RollbackHint(step_id=step.step_id, system=self.system, instruction="noop")


def test_cannot_instantiate_abstract_port() -> None:
    with pytest.raises(TypeError):
        IntegrationAdapter()  # type: ignore[abstract]


def test_concrete_adapter_satisfies_port() -> None:
    adapter = _FakeAdapter()
    assert adapter.system == "fake"
    assert adapter.capabilities()[0].kind is CapabilityKind.READ
    assert adapter.read(ReadQuery(capability="fake.read_thing")).data == {"ok": True}

    step = ExecutionStep(step_id="s1", capability=CapabilityRef(system="fake", name="fake.do"))
    assert adapter.execute(step, RunMode.DRY_RUN).status is StepStatus.DRY_RUN
    assert adapter.execute(step, RunMode.LIVE).status is StepStatus.OK
