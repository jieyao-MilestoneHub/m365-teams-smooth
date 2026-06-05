"""Trial 3 — Vendor Access: ambiguous, over-broad request → least-privilege, time-boxed access."""

from __future__ import annotations

from app.config import Settings
from app.container import build_court_service
from app.domain import ApproverRole, ChangeStatus, PlanKind, VerdictType
from app.services.court_service import CourtService


def _service() -> CourtService:
    return build_court_service(
        Settings(force_all_mock=True, db_url="sqlite:///:memory:", dry_run_default=True)
    )


_REQUEST = "give the vendor access to Project X until the campaign is done"


def test_overbroad_request_becomes_least_privilege_and_time_boxed() -> None:
    service = _service()
    summary = service.submit_change(_REQUEST)

    assert summary.status == ChangeStatus.AWAITING_VERDICT.value
    assert summary.unsafe is True
    assert summary.plan_kind == PlanKind.SAFE_ALTERNATIVE.value
    assert "accept_alternative" in summary.verdict_options

    trial = service.get_trial(summary.thread_id)
    assert trial is not None and trial.options is not None

    grant = next(
        s for s in trial.options.steps if s.capability.name == "sharepoint.grant_folder_permission"
    )
    assert grant.params["path"] == "/ProjectX/LaunchAssets"  # narrowed to one folder
    assert grant.params["role"] == "read"  # read-only
    assert grant.params["expiry"] == "2026-06-30"  # time-boxed

    revoke = next(
        s for s in trial.options.steps if s.capability.name == "entra.schedule_access_revoke"
    )
    assert revoke.params["revoke_on"] == "2026-06-30"  # auto-revoke scheduled

    assert trial.quorum is not None
    roles = {a.role for a in trial.quorum.required_approvers}
    assert roles == {ApproverRole.MANAGER, ApproverRole.SECURITY_LEAD}


def test_accepting_grants_scoped_access_and_schedules_revoke() -> None:
    service = _service()
    summary = service.submit_change(_REQUEST)
    cast = service.cast_verdict(
        summary.thread_id, VerdictType.ACCEPT_ALTERNATIVE, selected_plan=PlanKind.SAFE_ALTERNATIVE
    )
    assert cast.execution_status == ChangeStatus.DONE.value

    trial = service.get_trial(summary.thread_id)
    assert trial is not None
    caps = {
        step.capability.name
        for step in (trial.options.steps if trial.options else [])
    }
    assert "entra.invite_guest" in caps
    assert "entra.schedule_access_revoke" in caps
