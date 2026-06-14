"""Trial 1 — Launch Slip: end-to-end through the fully-wired court (dry-run + verdict)."""

from __future__ import annotations

from app.config import Settings
from app.container import build_court_service
from app.domain import ApproverRole, ChangeStatus, PlanKind, RiskLevel, VerdictType
from app.services.court_service import CourtService
from tests.conftest import ALL_ROLE_DIRECTORY, APPROVER, REQUESTER


def _service() -> CourtService:
    return build_court_service(
        Settings(
            force_all_mock=True,
            db_url="sqlite:///:memory:",
            dry_run_default=True,
            approver_directory=ALL_ROLE_DIRECTORY,
        )
    )


_REQUEST = "slip the launch from 2026-06-10 to 2026-06-17"
_CONFLICT_REQUEST = "move the rehearsal to 2026-06-16"


def test_target_date_conflict_yields_a_safe_alternative_date() -> None:
    # 2026-06-16 collides with the seeded board review: the court refuses the date as posed
    # and the Defender proposes the next free day with the same four-system ripple.
    service = _service()
    summary = service.submit_change(_CONFLICT_REQUEST, requester=REQUESTER)

    assert summary.unsafe is True
    assert summary.plan_kind == PlanKind.SAFE_ALTERNATIVE.value
    assert "accept_alternative" in summary.verdict_options
    assert "approve" not in summary.verdict_options

    trial = service.get_trial(summary.thread_id)
    assert trial is not None and trial.impact is not None and trial.options is not None
    assert "schedule.target_date_conflict" in trial.impact.tags
    assert trial.options.supersedes_request is True
    move = next(
        s for s in trial.options.steps if s.capability.name == "github.update_milestone_due"
    )
    assert move.params["due_on"] == "2026-06-17"  # the next free day after the clash


def test_accepting_the_alternative_date_executes() -> None:
    service = _service()
    summary = service.submit_change(_CONFLICT_REQUEST, requester=REQUESTER)
    cast = service.cast_verdict(
        summary.thread_id,
        VerdictType.ACCEPT_ALTERNATIVE,
        selected_plan=PlanKind.SAFE_ALTERNATIVE,
        principal=APPROVER,
    )
    assert cast.execution_status == ChangeStatus.DONE.value


def test_launch_slip_produces_medium_risk_court_held_for_review() -> None:
    service = _service()
    summary = service.submit_change(_REQUEST, requester=REQUESTER)

    assert summary.status == ChangeStatus.AWAITING_REQUESTER_REVIEW.value
    # A clean, coordinated reschedule: the milestone move is medium-severity and nothing fired
    # higher — approval is still required, but it is not the gravest (high) band, which is
    # reserved for unsafe outcomes (a date conflict or a latent breach).
    assert summary.risk_level == RiskLevel.MEDIUM.value
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
    summary = service.submit_change(_REQUEST, requester=REQUESTER)
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
    summary = service.submit_change(_REQUEST, requester=REQUESTER)

    cast = service.cast_verdict(summary.thread_id, VerdictType.APPROVE, principal=APPROVER)
    assert cast.execution_status == ChangeStatus.DONE.value
    assert cast.audit_id is not None

    trial = service.get_trial(summary.thread_id)
    assert trial is not None
    # dry-run: every executed step is predicted, not applied
    assert all(r.status.value == "dry_run" for r in trial.results)

    # casting the same verdict again is a no-op
    again = service.cast_verdict(summary.thread_id, VerdictType.APPROVE, principal=APPROVER)
    assert again.idempotent is True
    assert again.audit_id == cast.audit_id
