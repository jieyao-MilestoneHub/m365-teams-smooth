"""Trial — Weekly Report: scattered activity aggregates into one post, requester authority."""

from __future__ import annotations

from app.config import Settings
from app.container import build_court_service
from app.domain import ChangeStatus, PlanKind, RiskLevel
from app.services.court_service import CourtService
from tests.conftest import REQUESTER

_REQUEST = "post the Project X weekly report"


def _service() -> CourtService:
    return build_court_service(
        Settings(force_all_mock=True, db_url="sqlite:///:memory:", dry_run_default=True)
    )


def test_weekly_report_aggregates_and_executes_on_requester_confirmation() -> None:
    service = _service()
    summary = service.submit_change(_REQUEST, requester=REQUESTER)

    # Low risk, no approver: the requester's confirmation alone carries the authority.
    assert summary.status == ChangeStatus.AWAITING_REQUESTER_REVIEW.value
    assert summary.risk_level == RiskLevel.LOW.value
    assert summary.requires_approval is False
    assert summary.plan_kind == PlanKind.FEASIBLE.value

    sent = service.send_for_approval(summary.thread_id, actor=REQUESTER, note="posting it")
    assert sent.status == ChangeStatus.DONE.value

    trial = service.get_trial(summary.thread_id)
    assert trial is not None and trial.impact is not None and trial.options is not None
    assert "report.activity_collected" in trial.impact.tags
    # evidence spans the scattered sources: closed issues, tasks, meetings
    kinds = {item.kind for item in trial.impact.items}
    assert {"closed_issues", "tasks", "calendar"}.issubset(kinds)

    # one post, composed from the gathered counts (4 closed issues / 2 tasks / 1 meeting seeded)
    assert [s.capability.name for s in trial.options.steps] == ["teams.post_message"]
    message = str(trial.options.steps[0].params["message"])
    assert "4 issue(s) closed" in message
    assert "2 task(s) tracked" in message
    assert "1 meeting(s) held" in message
    assert trial.quorum is not None and trial.quorum.required_approvers == []
