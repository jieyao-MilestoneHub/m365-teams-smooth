"""Trial 2 — Customer Promise: the court refuses the unsafe GA promise and proposes a safe path."""

from __future__ import annotations

from app.config import Settings
from app.container import build_court_service
from app.domain import ApproverRole, ChangeStatus, PlanKind, VerdictType
from app.services.court_service import CourtService


def _service() -> CourtService:
    return build_court_service(
        Settings(force_all_mock=True, db_url="sqlite:///:memory:", dry_run_default=True)
    )


_REQUEST = "promise Customer A that SSO is GA by 2026-06-17"


def test_promise_is_rejected_with_a_safe_alternative() -> None:
    service = _service()
    summary = service.submit_change(_REQUEST)

    assert summary.status == ChangeStatus.AWAITING_VERDICT.value
    assert summary.unsafe is True
    assert summary.plan_kind == PlanKind.SAFE_ALTERNATIVE.value
    # an unsafe request is not simply "approve"-able; the alternative must be accepted
    assert "accept_alternative" in summary.verdict_options
    assert "approve" not in summary.verdict_options

    trial = service.get_trial(summary.thread_id)
    assert trial is not None and trial.options is not None
    # the five artifacts of the safe alternative
    assert {s.capability.name for s in trial.options.steps} == {
        "github.comment_issue",
        "outlook.create_event",
        "crm.add_note",
        "outlook.draft_email",
        "teams.create_escalation_thread",
    }
    assert trial.options.supersedes_request is True
    assert trial.quorum is not None
    roles = {a.role for a in trial.quorum.required_approvers}
    assert roles == {ApproverRole.SECURITY_LEAD, ApproverRole.ACCOUNT_OWNER}


def test_accepting_the_alternative_executes_the_safe_plan() -> None:
    service = _service()
    summary = service.submit_change(_REQUEST)

    cast = service.cast_verdict(
        summary.thread_id, VerdictType.ACCEPT_ALTERNATIVE, selected_plan=PlanKind.SAFE_ALTERNATIVE
    )
    assert cast.status == ChangeStatus.DONE.value

    trial = service.get_trial(summary.thread_id)
    assert trial is not None
    # the customer email is produced as a draft, never sent
    assert {r.step_id for r in trial.results} == {"s1", "s2", "s3", "s4", "s5"}
    assert all(r.status.value == "dry_run" for r in trial.results)
