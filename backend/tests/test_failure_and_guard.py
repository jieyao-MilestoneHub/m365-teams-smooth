"""Safety: the hallucination guard rejects unsupported actions; a failed step is contained."""

from __future__ import annotations

from app.config import Settings
from app.container import build_court_service
from app.domain import ChangeStatus, RunMode, StepStatus, VerdictType
from tests.conftest import build_mock_registry


def _settings() -> Settings:
    return Settings(force_all_mock=True, db_url="sqlite:///:memory:", dry_run_default=True)


def test_hallucination_guard_rejects_delete_repo() -> None:
    service = build_court_service(_settings())
    summary = service.submit_change(
        "slip the launch from 2026-06-10 to 2026-06-17, also delete the old launch repo"
    )

    # The unsupported action is rejected and recorded, not planned or executed.
    assert any("github.delete_repo" in e for e in summary.errors)
    trial = service.get_trial(summary.thread_id)
    assert trial is not None and trial.options is not None
    assert all("delete" not in s.capability.name for s in trial.options.steps)
    # the supported part of the request still proceeds
    assert summary.status == ChangeStatus.AWAITING_VERDICT.value


def test_partial_failure_is_contained_with_rollback() -> None:
    failing = build_mock_registry(planner_fail_on="planner.shift_task_dates")
    service = build_court_service(_settings(), registry=failing)

    summary = service.submit_change(
        "slip the launch from 2026-06-10 to 2026-06-17", run_mode=RunMode.LIVE
    )
    cast = service.cast_verdict(summary.thread_id, VerdictType.APPROVE)  # must not crash

    assert cast.status == ChangeStatus.FAILED.value
    trial = service.get_trial(summary.thread_id)
    assert trial is not None
    failed = [r for r in trial.results if r.status is StepStatus.FAILED]
    assert failed and failed[0].rollback is not None  # contained with a rollback hint
    # the other steps still ran (the run did not crash)
    assert any(r.status is StepStatus.OK for r in trial.results)
