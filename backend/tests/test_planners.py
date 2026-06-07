"""The planners build a feasible ripple plan, or safe alternatives for unsafe requests."""

from __future__ import annotations

from app.agent.planners import plan_launch, plan_project_access, plan_sso_ga
from app.domain import (
    Change,
    EvidenceItem,
    ImpactEvidence,
    PlanKind,
    RequestedAction,
)


def test_launch_plan_is_feasible_and_ripples() -> None:
    impact = ImpactEvidence(
        items=[
            EvidenceItem(
                system="github", kind="milestone", summary="", data={"due_on": "2026-06-10"}
            )
        ],
        tags=["schedule.milestone_move"],
    )
    plan = plan_launch(Change(change_id="c1", raw_request="x", due_by="2026-06-17"), impact)
    assert plan.kind is PlanKind.FEASIBLE
    caps = {s.capability.name for s in plan.steps}
    # the launch ripple spans four systems: GitHub, Outlook, Planner, Teams
    assert caps == {
        "github.update_milestone_due",
        "outlook.create_event",
        "planner.shift_task_dates",
        "teams.update_announcement",
    }
    shift = next(s for s in plan.steps if s.capability.name == "planner.shift_task_dates")
    assert shift.params["delta_days"] == 7  # 2026-06-10 -> 2026-06-17


def test_launch_plan_accepts_timestamped_evidence_dates() -> None:
    # Live evidence carries full timestamps (GitHub returns 2026-06-10T00:00:00Z), not plain dates.
    impact = ImpactEvidence(
        items=[
            EvidenceItem(
                system="github",
                kind="milestone",
                summary="",
                data={"due_on": "2026-06-10T00:00:00Z"},
            )
        ],
        tags=["schedule.milestone_move"],
    )
    plan = plan_launch(Change(change_id="c1", raw_request="x", due_by="2026-06-17"), impact)
    shift = next(s for s in plan.steps if s.capability.name == "planner.shift_task_dates")
    assert shift.params["delta_days"] == 7


def test_sso_ga_plan_is_a_safe_alternative_with_all_artifacts() -> None:
    impact = ImpactEvidence(
        items=[
            EvidenceItem(
                system="outlook",
                kind="security_review",
                summary="",
                data={"review_date": "2026-06-18"},
            )
        ],
        tags=["security.review_after_due_date"],
    )
    plan = plan_sso_ga(Change(change_id="c1", raw_request="x", due_by="2026-06-17"), impact)
    assert plan.kind is PlanKind.SAFE_ALTERNATIVE
    assert plan.supersedes_request is True
    caps = {s.capability.name for s in plan.steps}
    assert caps == {
        "github.comment_issue",
        "outlook.create_event",
        "crm.add_note",
        "outlook.draft_email",  # a draft, never sent
        "teams.create_escalation_thread",
    }


def test_sso_ga_comment_targets_the_evidenced_blocker() -> None:
    # Live evidence carries the real open blockers; the comment must land on one of them,
    # not on a fixture issue number that may not exist in the configured repository.
    impact = ImpactEvidence(
        items=[
            EvidenceItem(
                system="github",
                kind="blockers",
                summary="",
                data={
                    "issues": [{"number": 181, "state": "open"}, {"number": 180, "state": "open"}]
                },
            ),
            EvidenceItem(
                system="outlook",
                kind="security_review",
                summary="",
                data={"review_date": "2026-06-18"},
            ),
        ],
        tags=["github.blocking_issues_open", "security.review_after_due_date"],
    )
    plan = plan_sso_ga(Change(change_id="c1", raw_request="x", due_by="2026-06-17"), impact)
    comment = next(s for s in plan.steps if s.capability.name == "github.comment_issue")
    assert comment.params["issue"] == 180  # the lowest-numbered open blocker


def test_sso_ga_comment_falls_back_to_the_fixture_blocker() -> None:
    impact = ImpactEvidence(
        items=[
            EvidenceItem(
                system="outlook",
                kind="security_review",
                summary="",
                data={"review_date": "2026-06-18"},
            )
        ],
        tags=["security.review_after_due_date"],
    )
    plan = plan_sso_ga(Change(change_id="c1", raw_request="x", due_by="2026-06-17"), impact)
    comment = next(s for s in plan.steps if s.capability.name == "github.comment_issue")
    assert comment.params["issue"] == 42


def test_vendor_access_plan_is_least_privilege_and_time_boxed() -> None:
    impact = ImpactEvidence(tags=["access.overbroad_scope", "access.ambiguous_duration"])
    change = Change(
        change_id="c1",
        raw_request="x",
        requested_actions=[
            RequestedAction(
                system="sharepoint",
                capability_name="sharepoint.grant_folder_permission",
                params={"path": "/ProjectX", "principal": "v@example.com", "role": "write"},
            )
        ],
    )
    plan = plan_project_access(change, impact)
    assert plan.kind is PlanKind.SAFE_ALTERNATIVE
    grant = next(s for s in plan.steps if s.capability.name == "sharepoint.grant_folder_permission")
    assert grant.params["path"] == "/ProjectX/LaunchAssets"  # narrowed
    assert grant.params["role"] == "read"  # read-only
    assert grant.params["expiry"] == "2026-06-30"  # time-boxed
    # auto-revoke is scheduled
    assert any(s.capability.name == "entra.schedule_access_revoke" for s in plan.steps)
