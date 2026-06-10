"""Golden fixtures: the expected court output for each of the three trials, in one table.

A single parametrized regression over the fully-wired court. If a trial's risk, safety, plan,
verdict options, or quorum drifts from these golden values, this fails.
"""

from __future__ import annotations

import pytest

from app.config import Settings
from app.container import build_court_service
from app.services.court_service import CourtService


def _service() -> CourtService:
    return build_court_service(
        Settings(force_all_mock=True, db_url="sqlite:///:memory:", dry_run_default=True)
    )


GOLDEN: dict[str, dict[str, object]] = {
    "launch_slip": {
        "request": "slip the launch from 2026-06-10 to 2026-06-17",
        "status": "awaiting_verdict",
        "risk_level": "high",
        "unsafe": False,
        "plan_kind": "feasible",
        "verdict_options": {"approve", "approve_internal_only", "request_revision", "reject"},
        "plan_capabilities": {
            "github.update_milestone_due",
            "outlook.create_event",
            "planner.shift_task_dates",
            "teams.update_announcement",
        },
        "approvers": {"eng_lead", "comms"},
    },
    "launch_sla_breach": {
        # The requested day is free on the calendar, but cross-referencing CRM (SLA), SharePoint
        # (release freeze), and GitHub (go-live buffer) reveals a latent breach no single system
        # shows. Refused as posed; the latest date honoring every constraint (2026-06-18) proposed.
        "request": "move the launch rehearsal to 2026-06-22",
        "status": "awaiting_verdict",
        "risk_level": "high",
        "unsafe": True,
        "plan_kind": "safe_alternative",
        "verdict_options": {"accept_alternative", "request_revision", "reject"},
        "plan_capabilities": {
            "github.update_milestone_due",
            "outlook.create_event",
            "planner.shift_task_dates",
            "teams.update_announcement",
        },
        "approvers": {"eng_lead", "comms", "account_owner"},
    },
    "customer_promise": {
        "request": "promise Customer A that SSO is GA by 2026-06-17",
        "status": "awaiting_verdict",
        "risk_level": "high",
        "unsafe": True,
        "plan_kind": "safe_alternative",
        "verdict_options": {"accept_alternative", "request_revision", "reject"},
        "plan_capabilities": {
            "github.comment_issue",
            "outlook.create_event",
            "crm.add_note",
            "outlook.draft_email",
            "teams.create_escalation_thread",
        },
        "approvers": {"security_lead", "account_owner"},
    },
    "rehearsal_conflict": {
        # The requested day collides with the seeded board review: refused as posed, the next
        # free day proposed instead — the safe-alternative path inside the everyday reschedule.
        "request": "move the rehearsal to 2026-06-16",
        "status": "awaiting_verdict",
        "risk_level": "high",
        "unsafe": True,
        "plan_kind": "safe_alternative",
        "verdict_options": {"accept_alternative", "request_revision", "reject"},
        "plan_capabilities": {
            "github.update_milestone_due",
            "outlook.create_event",
            "planner.shift_task_dates",
            "teams.update_announcement",
        },
        "approvers": {"eng_lead", "comms"},
    },
    "meeting_actions": {
        "request": "create action items from standup",
        "status": "done",  # low risk, no approver: auto-approved and executed in one pass
        "risk_level": "low",
        "unsafe": False,
        "plan_kind": "feasible",
        "verdict_options": {"approve", "request_revision", "reject"},
        "plan_capabilities": {"planner.create_task", "outlook.create_event"},
        "approvers": set(),
    },
    "weekly_report": {
        "request": "post the Project X weekly report",
        "status": "done",  # low risk, no approver: auto-approved and executed in one pass
        "risk_level": "low",
        "unsafe": False,
        "plan_kind": "feasible",
        "verdict_options": {"approve", "request_revision", "reject"},
        "plan_capabilities": {"teams.post_message"},
        "approvers": set(),
    },
    "vendor_access": {
        "request": "give the vendor access to Project X until the campaign is done",
        "status": "awaiting_verdict",
        "risk_level": "high",
        "unsafe": True,
        "plan_kind": "safe_alternative",
        "verdict_options": {"accept_alternative", "request_revision", "reject"},
        "plan_capabilities": {
            "sharepoint.grant_folder_permission",
            "entra.invite_guest",
            "entra.schedule_access_revoke",
        },
        "approvers": {"manager", "security_lead"},
    },
}


@pytest.mark.parametrize("trial", list(GOLDEN))
def test_trial_matches_golden(trial: str) -> None:
    golden = GOLDEN[trial]
    service = _service()
    summary = service.submit_change(str(golden["request"]))

    assert summary.status == golden["status"]
    assert summary.risk_level == golden["risk_level"]
    assert summary.unsafe is golden["unsafe"]
    assert summary.plan_kind == golden["plan_kind"]
    assert set(summary.verdict_options) == golden["verdict_options"]

    court = service.get_trial(summary.thread_id)
    assert court is not None and court.options is not None and court.quorum is not None
    assert {s.capability.name for s in court.options.steps} == golden["plan_capabilities"]
    assert {a.role.value for a in court.quorum.required_approvers} == golden["approvers"]
