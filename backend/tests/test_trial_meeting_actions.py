"""Trial — Meeting Actions: spoken standup follow-ups become tracked tasks, requester authority."""

from __future__ import annotations

from app.config import Settings
from app.container import build_court_service
from app.domain import ChangeStatus, PlanKind, Principal, RiskLevel
from app.services.court_service import CourtService
from tests.conftest import REQUESTER

_REQUEST = "create action items from standup"


def _service(**overrides: object) -> CourtService:
    return build_court_service(
        Settings(
            force_all_mock=True,
            db_url="sqlite:///:memory:",
            dry_run_default=True,
            **overrides,  # type: ignore[arg-type]
        )
    )


def test_action_items_become_tracked_tasks_and_execute_low_risk() -> None:
    service = _service()
    summary = service.submit_change(_REQUEST, requester=REQUESTER)

    # Low risk, no approver: the requester's own confirmation executes the plan.
    assert summary.status == ChangeStatus.AWAITING_REQUESTER_REVIEW.value
    assert summary.risk_level == RiskLevel.LOW.value
    assert summary.requires_approval is False
    assert summary.unsafe is False
    assert summary.plan_kind == PlanKind.FEASIBLE.value

    sent = service.send_for_approval(summary.thread_id, actor=REQUESTER, note="tracking these")
    assert sent.status == ChangeStatus.DONE.value

    trial = service.get_trial(summary.thread_id)
    assert trial is not None and trial.impact is not None and trial.options is not None
    assert "meeting.action_items_found" in trial.impact.tags

    # Three dated follow-ups become tasks with their owners; the undated review gets a slot.
    tasks = [s for s in trial.options.steps if s.capability.name == "planner.create_task"]
    assert len(tasks) == 3
    assert {str(t.params["assignee"]) for t in tasks} == {"Alex", "Jamie", "PM"}
    assert {str(t.params["due"]) for t in tasks} == {"2026-06-12", "2026-06-13", "2026-06-14"}
    reviews = [s for s in trial.options.steps if s.capability.name == "outlook.create_event"]
    assert len(reviews) == 1

    # No approver was ever required — the quorum is empty by policy, not by accident.
    assert trial.quorum is not None and trial.quorum.required_approvers == []


def test_requester_confirmation_alone_executes() -> None:
    # With identities configured, the trial holds at the requester's review gate; their
    # confirmation carries the authority — no approver round-trip for low-risk tracking.
    requester = Principal(oid="oid-req", upn="req@example.com", display_name="Rae Quester")
    service = _service(approver_directory="manager:oid-someone-else")

    summary = service.submit_change(_REQUEST, requester=requester)
    assert summary.status == ChangeStatus.AWAITING_REQUESTER_REVIEW.value

    sent = service.send_for_approval(summary.thread_id, actor=requester, note="tracking these")
    assert sent.status == ChangeStatus.DONE.value
