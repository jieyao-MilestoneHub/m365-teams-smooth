"""Trial 1 — Launch Slip: end-to-end through the fully-wired court (dry-run + verdict)."""

from __future__ import annotations

from app.config import Settings
from app.container import build_court_service
from app.domain import ApproverRole, ChangeStatus, PlanKind, RiskLevel, VerdictType
from app.services.court_service import CourtService


def _service() -> CourtService:
    return build_court_service(
        Settings(force_all_mock=True, db_url="sqlite:///:memory:", dry_run_default=True)
    )


_REQUEST = "slip the launch from 2026-06-10 to 2026-06-17"


def test_launch_slip_produces_high_risk_court_awaiting_verdict() -> None:
    service = _service()
    summary = service.submit_change(_REQUEST)

    assert summary.status == ChangeStatus.AWAITING_VERDICT.value
    assert summary.risk_level == RiskLevel.HIGH.value
    assert summary.requires_approval is True
    assert summary.unsafe is False  # feasible, not unsafe
    assert summary.plan_kind == PlanKind.FEASIBLE.value
    # the four verdict options the card offers
    assert set(summary.verdict_options) == {
        "approve",
        "approve_internal_only",
        "request_revision",
        "reject",
    }

    trial = service.get_trial(summary.thread_id)
    assert trial is not None and trial.impact is not None
    # impact evidence spans the ripple: milestone, calendar, planner, announcement
    kinds = {item.kind for item in trial.impact.items}
    assert {"milestone", "calendar", "tasks", "announcement"}.issubset(kinds)
    # quorum requires the engineering lead and comms
    assert trial.quorum is not None
    roles = {a.role for a in trial.quorum.required_approvers}
    assert roles == {ApproverRole.ENG_LEAD, ApproverRole.COMMS}


def test_every_plan_step_references_a_registered_capability() -> None:
    service = _service()
    summary = service.submit_change(_REQUEST)
    trial = service.get_trial(summary.thread_id)
    assert trial is not None and trial.options is not None
    expected = {
        "github.update_milestone_due",
        "outlook.create_event",
        "planner.shift_task_dates",
        "teams.update_announcement",
    }
    assert {step.capability.name for step in trial.options.steps} == expected


def test_dry_run_then_approve_completes_and_audits_dry_run() -> None:
    service = _service()
    summary = service.submit_change(_REQUEST)

    cast = service.cast_verdict(summary.thread_id, VerdictType.APPROVE)
    assert cast.execution_status == ChangeStatus.DONE.value
    assert cast.audit_id is not None

    trial = service.get_trial(summary.thread_id)
    assert trial is not None
    # dry-run: every executed step is predicted, not applied
    assert all(r.status.value == "dry_run" for r in trial.results)

    # casting the same verdict again is a no-op
    again = service.cast_verdict(summary.thread_id, VerdictType.APPROVE)
    assert again.idempotent is True
    assert again.audit_id == cast.audit_id
