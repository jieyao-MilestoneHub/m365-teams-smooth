"""Effect verification: live writes are checked against the reviewed plan, dry runs are not."""

from __future__ import annotations

from app.agent.nodes.verify import VerifyNode
from app.agent.state import initial_state, serialize
from app.domain import (
    CapabilityRef,
    ExecutionPlan,
    ExecutionStep,
    PlanKind,
    RunMode,
    StepResult,
    StepStatus,
)
from app.domain.verification import verify_effect


def test_verify_effect_matches_mismatches_and_skips_unreported_keys() -> None:
    verification = verify_effect(
        "s1",
        params={"due_on": "2026-06-17", "milestone": "Launch", "note": "unreported"},
        after={"due_on": "2026-06-10", "milestone": "Launch", "url": "https://x"},
    )
    assert verification.matched is False
    assert verification.checked == ["due_on", "milestone"]  # 'note' not reported by the system
    assert verification.mismatches == ["due_on: expected '2026-06-17', got '2026-06-10'"]

    clean = verify_effect("s1", params={"milestone": "Launch"}, after={"milestone": "Launch"})
    assert clean.matched is True and clean.mismatches == []


def _state(run_mode: RunMode, results: list[StepResult]) -> dict[str, object]:
    state = initial_state(
        thread_id="t1", change_id="c1", raw_request="x", source="t", run_mode=run_mode
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
    state["options"] = serialize(plan)
    state["results"] = [serialize(r) for r in results]
    return dict(state)


def test_live_mismatch_is_recorded() -> None:
    results = [
        StepResult(step_id="s1", status=StepStatus.OK, after={"due_on": "2026-06-10"}),
        StepResult(step_id="s2", status=StepStatus.FAILED, error="boom"),  # skipped: not OK
    ]
    update = VerifyNode()(_state(RunMode.LIVE, results))  # type: ignore[arg-type]

    verifications = update["verifications"]
    assert isinstance(verifications, list) and len(verifications) == 1
    first = verifications[0]
    assert isinstance(first, dict)
    assert first["matched"] is False
    mismatches = first["mismatches"]
    assert isinstance(mismatches, list) and "due_on" in str(mismatches[0])


def test_live_match_is_recorded_as_clean() -> None:
    results = [StepResult(step_id="s1", status=StepStatus.OK, after={"due_on": "2026-06-17"})]
    update = VerifyNode()(_state(RunMode.LIVE, results))  # type: ignore[arg-type]
    verifications = update["verifications"]
    assert isinstance(verifications, list)
    first = verifications[0]
    assert isinstance(first, dict) and first["matched"] is True


def test_dry_run_skips_verification() -> None:
    results = [StepResult(step_id="s1", status=StepStatus.DRY_RUN)]
    update = VerifyNode()(_state(RunMode.DRY_RUN, results))  # type: ignore[arg-type]
    assert update == {}
