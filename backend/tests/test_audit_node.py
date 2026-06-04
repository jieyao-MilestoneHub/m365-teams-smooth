"""The audit node assembles an append-only record with before/after and rollback hints."""

from __future__ import annotations

from app.agent.nodes.audit import AuditNode
from app.agent.state import CourtState, initial_state, serialize
from app.domain import (
    AuditRecord,
    CapabilityRef,
    Change,
    ChangeStatus,
    ExecutionPlan,
    ExecutionStep,
    PlanKind,
    RollbackHint,
    RunMode,
    StepResult,
    StepStatus,
)
from app.ports.repository import AuditRepository


class _MemAudit(AuditRepository):
    def __init__(self) -> None:
        self.records: list[AuditRecord] = []

    def append(self, record: AuditRecord) -> None:
        self.records.append(record)

    def get(self, audit_id: str) -> AuditRecord | None:
        return next((r for r in self.records if r.audit_id == audit_id), None)

    def latest_for_change(self, change_id: str) -> AuditRecord | None:
        matches = [r for r in self.records if r.change_id == change_id]
        return matches[-1] if matches else None

    def thread_ids_completed_before(self, cutoff: str) -> list[str]:
        latest: dict[str, str] = {}
        for r in self.records:
            latest[r.thread_id] = max(latest.get(r.thread_id, ""), r.created_at)
        return [tid for tid, at in latest.items() if at < cutoff]


def _state() -> CourtState:
    state = initial_state(
        thread_id="t1", change_id="c1", raw_request="slip", source="t", run_mode=RunMode.LIVE
    )
    state["change"] = serialize(Change(change_id="c1", raw_request="slip"))
    state["options"] = serialize(
        ExecutionPlan(
            kind=PlanKind.FEASIBLE,
            steps=[
                ExecutionStep(
                    step_id="s1",
                    capability=CapabilityRef(system="github", name="github.update_milestone_due"),
                )
            ],
        )
    )
    state["results"] = [
        serialize(
            StepResult(
                step_id="s1",
                status=StepStatus.OK,
                before={"due_on": "2026-06-10"},
                after={"due_on": "2026-06-17"},
                rollback=RollbackHint(step_id="s1", system="github", instruction="restore"),
            )
        )
    ]
    state["status"] = ChangeStatus.DONE.value
    return state


def test_audit_record_is_appended_with_snapshots_and_rollback() -> None:
    repo = _MemAudit()
    node = AuditNode(repo, clock=lambda: "2026-06-02T00:00:00Z", id_factory=lambda: "a1")

    result = node(_state())

    assert result["audit_id"] == "a1"
    record = repo.get("a1")
    assert record is not None
    assert record.run_mode is RunMode.LIVE
    assert record.before_after[0].before == {"due_on": "2026-06-10"}
    assert record.before_after[0].system == "github"
    assert record.rollback_hints[0].instruction == "restore"
    assert record.trial.options is not None


def test_snapshots_and_hints_are_derived_not_stored() -> None:
    repo = _MemAudit()
    node = AuditNode(repo, clock=lambda: "2026-06-02T00:00:00Z", id_factory=lambda: "a1")
    node(_state())
    record = repo.get("a1")
    assert record is not None

    # The persisted payload carries each fact once: snapshots/hints live in trial.results only.
    payload = record.model_dump(mode="json")
    assert "before_after" not in payload
    assert "rollback_hints" not in payload
    # The views still derive from the results for any consumer that wants them.
    assert record.before_after and record.rollback_hints


def test_legacy_payloads_with_stored_duplicates_still_validate() -> None:
    repo = _MemAudit()
    node = AuditNode(repo, clock=lambda: "2026-06-02T00:00:00Z", id_factory=lambda: "a1")
    node(_state())
    record = repo.get("a1")
    assert record is not None

    legacy = record.model_dump(mode="json")
    legacy["before_after"] = [b.model_dump(mode="json") for b in record.before_after]
    legacy["rollback_hints"] = [r.model_dump(mode="json") for r in record.rollback_hints]
    revived = AuditRecord.model_validate(legacy)  # extras are ignored, views still derive
    assert revived.before_after[0].system == "github"
