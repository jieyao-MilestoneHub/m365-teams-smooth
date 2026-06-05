"""Per-trial planners: a feasible plan, or the safe alternative when the request is unsafe.

This is the court's differentiator. Launch Slip is feasible (the milestone move, expanded to its
dependent schedule and comms updates). Customer Promise and Vendor Access are unsafe as asked, so
their planners produce a *safe alternative* — a private preview with gated GA, and least-privilege
time-boxed access — that supersedes the request. Registered in ``PLANNERS`` for the options node.
"""

from __future__ import annotations

from datetime import date

from app.agent.nodes.options import feasible_from_actions
from app.domain import (
    CapabilityRef,
    Change,
    ExecutionPlan,
    ExecutionStep,
    ImpactEvidence,
    PlanKind,
)


def _step(step_id: str, system: str, capability: str, params: dict[str, object]) -> ExecutionStep:
    return ExecutionStep(
        step_id=step_id, capability=CapabilityRef(system=system, name=capability), params=params
    )


def _evidence_field(impact: ImpactEvidence, kind: str, field: str) -> str | None:
    item = next((i for i in impact.items if i.kind == kind), None)
    if item is None:
        return None
    value = item.data.get(field)
    return str(value) if value is not None else None


def _as_day(value: str) -> date:
    """The calendar day of an ISO date or timestamp — live evidence carries full timestamps
    (GitHub returns ``2026-06-10T00:00:00Z``), while parsed requests carry plain dates."""
    return date.fromisoformat(value[:10])


def plan_launch(change: Change, impact: ImpactEvidence) -> ExecutionPlan:
    """Feasible: move the milestone and ripple into calendar, planner, and the announcement."""
    new_due = change.due_by or "2026-06-17"
    old_due = _evidence_field(impact, "milestone", "due_on") or "2026-06-10"
    delta = (_as_day(new_due) - _as_day(old_due)).days
    steps = [
        _step(
            "s1",
            "github",
            "github.update_milestone_due",
            {"milestone": "Launch", "due_on": new_due},
        ),
        _step(
            "s2",
            "outlook",
            "outlook.create_event",
            {"title": f"Launch review: moved to {new_due}", "start": new_due},
        ),
        _step("s3", "planner", "planner.shift_task_dates", {"delta_days": delta}),
        _step(
            "s4",
            "teams",
            "teams.update_announcement",
            {"channel": "launch", "message": f"Launch has moved to {new_due}."},
        ),
    ]
    return ExecutionPlan(
        kind=PlanKind.FEASIBLE,
        steps=steps,
        rationale=f"Move the launch to {new_due}; update calendar, schedule, and announcement.",
    )


def plan_sso_ga(change: Change, impact: ImpactEvidence) -> ExecutionPlan:
    """Safe alternative: refuse GA; offer a private preview, with GA gated on the review."""
    if "security.review_after_due_date" not in impact.tags:
        return feasible_from_actions(change)

    promised = change.due_by or "2026-06-17"
    ga_date = _evidence_field(impact, "security_review", "review_date") or "2026-06-18"
    comment = f"Customer commitment {promised}: private preview only; GA pending review."
    email_body = (
        f"We can offer a private preview on {promised}; general availability will "
        f"follow the security review on {ga_date}."
    )
    steps = [
        _step("s1", "github", "github.comment_issue", {"issue": 42, "body": comment}),
        _step(
            "s2",
            "outlook",
            "outlook.create_event",
            {"title": "SSO security review", "start": ga_date},
        ),
        _step(
            "s3",
            "crm",
            "crm.add_note",
            {"account": "Customer A", "note": "Do not promise GA; offer a private preview."},
        ),
        _step(
            "s4",
            "outlook",
            "outlook.draft_email",
            {
                "to": "customer-a@example.com",
                "subject": "SSO availability timeline",
                "body": email_body,
            },
        ),
        _step(
            "s5",
            "teams",
            "teams.create_escalation_thread",
            {
                "channel": "deals",
                "title": "SSO GA commitment risk",
                "body": "Review before any GA promise.",
            },
        ),
    ]
    return ExecutionPlan(
        kind=PlanKind.SAFE_ALTERNATIVE,
        steps=steps,
        supersedes_request=True,
        rationale=(
            f"Reject the GA promise: offer a private preview on {promised}, "
            f"with GA pending the security review on {ga_date}."
        ),
    )


def plan_project_access(change: Change, impact: ImpactEvidence) -> ExecutionPlan:
    """Safe alternative: least-privilege, time-boxed access with auto-revoke."""
    unsafe = {"access.overbroad_scope", "access.ambiguous_duration"}
    if not unsafe.intersection(impact.tags):
        return feasible_from_actions(change)

    expiry = "2026-06-30"
    action = next((a for a in change.requested_actions if a.system == "sharepoint"), None)
    principal = "vendor@example.com"
    if action is not None:
        principal = str(action.params.get("principal", principal))
    grant_params: dict[str, object] = {
        "path": "/ProjectX/LaunchAssets",
        "principal": principal,
        "role": "read",
        "expiry": expiry,
    }
    steps = [
        _step("s1", "sharepoint", "sharepoint.grant_folder_permission", grant_params),
        _step("s2", "entra", "entra.invite_guest", {"email": principal, "display_name": "Vendor"}),
        _step(
            "s3",
            "entra",
            "entra.schedule_access_revoke",
            {"principal": principal, "revoke_on": expiry},
        ),
    ]
    return ExecutionPlan(
        kind=PlanKind.SAFE_ALTERNATIVE,
        steps=steps,
        supersedes_request=True,
        rationale=(
            "Grant least-privilege read-only access to /ProjectX/LaunchAssets "
            f"until {expiry}, then auto-revoke."
        ),
    )


PLANNERS = {
    "launch": plan_launch,
    "sso-ga": plan_sso_ga,
    "project-access": plan_project_access,
}
