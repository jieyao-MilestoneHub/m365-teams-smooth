"""Domain models construct and round-trip through JSON-safe dicts (checkpoint-safe)."""

from __future__ import annotations

from app.domain import (
    AuditRecord,
    Capability,
    CapabilityKind,
    CapabilityRef,
    Change,
    ChangeStatus,
    Deliberation,
    DeliberationEntry,
    ExecutionPlan,
    ExecutionStep,
    PlanKind,
    RequestedAction,
    RunMode,
    StepResult,
    StepStatus,
    TrialRecord,
)


def test_capability_validates_kind() -> None:
    cap = Capability(system="github", name="github.update_milestone_due", kind=CapabilityKind.WRITE)
    assert cap.kind is CapabilityKind.WRITE


def test_change_defaults() -> None:
    change = Change(change_id="c1", raw_request="slip the launch")
    assert change.status is ChangeStatus.INTAKE
    assert change.unsafe is False
    assert change.requested_actions == []


def test_audit_record_round_trips_through_dict() -> None:
    """model_dump(mode='json') -> model_validate must be lossless (how state is checkpointed)."""
    change = Change(
        change_id="c1",
        raw_request="slip the launch",
        requested_actions=[
            RequestedAction(system="github", capability_name="github.update_milestone_due")
        ],
    )
    plan = ExecutionPlan(
        kind=PlanKind.FEASIBLE,
        steps=[
            ExecutionStep(
                step_id="s1",
                capability=CapabilityRef(system="github", name="github.update_milestone_due"),
                params={"due_on": "2026-06-17"},
            )
        ],
    )
    results = [StepResult(step_id="s1", status=StepStatus.DRY_RUN)]
    record = AuditRecord(
        audit_id="a1",
        change_id="c1",
        thread_id="t1",
        run_mode=RunMode.DRY_RUN,
        status=ChangeStatus.DONE,
        trial=TrialRecord(change=change, options=plan, results=results),
        created_at="2026-06-02T00:00:00Z",
    )

    dumped = record.model_dump(mode="json")
    restored = AuditRecord.model_validate(dumped)
    assert restored == record
    assert restored.trial.options is not None
    assert restored.trial.options.steps[0].capability.name == "github.update_milestone_due"


def test_deliberation_round_trips_and_defaults() -> None:
    entry = DeliberationEntry(node="policy", role="", rationale="Scored 80 (high).", source="llm")
    delib = Deliberation(entries=[entry])
    assert Deliberation().entries == []  # empty by default
    assert DeliberationEntry(node="intake", rationale="x").source == "llm"  # default provenance
    restored = Deliberation.model_validate(delib.model_dump(mode="json"))
    assert restored == delib
