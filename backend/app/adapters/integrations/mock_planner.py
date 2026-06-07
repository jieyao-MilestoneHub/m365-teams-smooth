"""Mock Planner adapter: read tasks, shift their due dates, and create tracked tasks.

Supports a failure injection (``fail_on``) so a trial can simulate a step failing mid-execution
and verify it is contained as a partial result with a rollback hint.
"""

from __future__ import annotations

from datetime import date, timedelta

from app.adapters.integrations.base import BaseIntegrationAdapter
from app.domain import (
    Capability,
    CapabilityKind,
    ExecutionStep,
    PredictedEffect,
    RollbackHint,
)
from app.domain.errors import IntegrationError
from app.ports.integration import ReadQuery, ReadResult

_SYSTEM = "planner"


def _shift(iso_day: str, delta_days: int) -> str:
    return (date.fromisoformat(iso_day) + timedelta(days=delta_days)).isoformat()


def _as_int(value: object) -> int:
    return int(value) if isinstance(value, (int, str)) else 0


class MockPlannerAdapter(BaseIntegrationAdapter):
    """In-memory Planner stand-in."""

    def __init__(self, *, fail_on: str | None = None) -> None:
        self._tasks: list[dict[str, object]] = [
            {"id": "T-1", "title": "Finalize release notes", "due": "2026-06-10"},
            {"id": "T-2", "title": "Cut release branch", "due": "2026-06-09"},
        ]
        self._fail_on = fail_on

    @property
    def system(self) -> str:
        return _SYSTEM

    def _capabilities(self) -> list[Capability]:
        return [
            Capability(system=_SYSTEM, name="planner.read_tasks", kind=CapabilityKind.READ),
            Capability(
                system=_SYSTEM,
                name="planner.shift_task_dates",
                kind=CapabilityKind.WRITE,
                params_schema={
                    "required": ["delta_days"],
                    "properties": {"delta_days": {"pattern": "^-?[0-9]+$"}},
                },
            ),
            Capability(
                system=_SYSTEM,
                name="planner.create_task",
                kind=CapabilityKind.WRITE,
                params_schema={
                    "required": ["title"],
                    "properties": {"due": {"format": "date"}},
                },
            ),
        ]

    def _read(self, query: ReadQuery) -> ReadResult:
        if query.capability == "planner.read_tasks":
            return ReadResult(capability=query.capability, data={"tasks": list(self._tasks)})
        raise IntegrationError(f"{_SYSTEM}: unknown read capability '{query.capability}'")

    def _predict(self, step: ExecutionStep, before: dict[str, object]) -> PredictedEffect:
        if step.capability.name == "planner.create_task":
            title = str(step.params.get("title", ""))
            due = str(step.params.get("due", ""))
            return PredictedEffect(
                summary=f"would create task '{title}'" + (f" due {due}" if due else ""),
                diff=dict(step.params),
            )
        delta = _as_int(step.params.get("delta_days", 0))
        return PredictedEffect(
            summary=f"would shift {len(self._tasks)} task(s) by {delta} day(s)",
            diff={"delta_days": delta, "task_count": len(self._tasks)},
        )

    def _apply(self, step: ExecutionStep) -> dict[str, object]:
        if self._fail_on == step.capability.name:
            raise IntegrationError(f"{_SYSTEM}: scheduling service unavailable")
        if step.capability.name == "planner.create_task":
            task: dict[str, object] = {
                "id": f"T-{len(self._tasks) + 1}",
                "title": str(step.params.get("title", "")),
            }
            for key in ("due", "assignee"):
                if step.params.get(key):
                    task[key] = str(step.params[key])
            self._tasks.append(task)
            return {"created": dict(task)}
        delta = _as_int(step.params.get("delta_days", 0))
        for task_row in self._tasks:
            task_row["due"] = _shift(str(task_row["due"]), delta)
        return {"shifted": len(self._tasks), "delta_days": delta}

    def _fetch_before(self, step: ExecutionStep) -> dict[str, object]:
        return {"tasks": [dict(t) for t in self._tasks]}

    def _rollback(self, step: ExecutionStep, before: dict[str, object]) -> RollbackHint:
        if step.capability.name == "planner.create_task":
            return RollbackHint(
                step_id=step.step_id,
                system=_SYSTEM,
                instruction="delete the created task",
                params={"title": str(step.params.get("title", ""))},
            )
        delta = _as_int(step.params.get("delta_days", 0))
        return RollbackHint(
            step_id=step.step_id,
            system=_SYSTEM,
            instruction=f"shift the affected tasks back by {delta} day(s)",
            params={"delta_days": -delta},
        )
