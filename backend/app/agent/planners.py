"""Per-trial planners: a feasible plan, or the safe alternative when the request is unsafe.

This is the court's differentiator. Launch Slip is feasible (the milestone move, expanded to its
dependent schedule and comms updates). Customer Promise and Vendor Access are unsafe as asked, so
their planners produce a *safe alternative* — a private preview with gated GA, and least-privilege
time-boxed access — that supersedes the request. Registered in ``PLANNERS`` for the options node.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

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


def _blocker_issue(impact: ImpactEvidence) -> int | None:
    """The lowest-numbered open blocker from evidence — the comment must land on a real issue,
    not a fixture number, when the GitHub adapter runs against a real repository."""
    item = next((i for i in impact.items if i.kind == "blockers"), None)
    if item is None:
        return None
    issues = item.data.get("issues")
    if not isinstance(issues, list):
        return None
    numbers: list[int] = []
    for issue in issues:
        if isinstance(issue, dict):
            number = issue.get("number")
            if isinstance(number, int):
                numbers.append(number)
    return min(numbers) if numbers else None


def _as_day(value: str) -> date:
    """The calendar day of an ISO date or timestamp — live evidence carries full timestamps
    (GitHub returns ``2026-06-10T00:00:00Z``), while parsed requests carry plain dates."""
    return date.fromisoformat(value[:10])


def _busy_days(impact: ImpactEvidence) -> set[str]:
    item = next((i for i in impact.items if i.kind == "calendar"), None)
    events = item.data.get("events") if item is not None else None
    if not isinstance(events, list):
        return set()
    return {str(e.get("start", ""))[:10] for e in events if isinstance(e, dict)}


def _next_free_day(after: date, busy: set[str]) -> str:
    day = after
    for _ in range(14):
        day = day + timedelta(days=1)
        if day.isoformat() not in busy:
            return day.isoformat()
    return (after + timedelta(days=1)).isoformat()


def _latest_safe_day(after: date, sla: str, freeze_start: str | None, busy: set[str]) -> str:
    """The latest day that honors every constraint: on/before the SLA, before the freeze, free.

    Walking forward from ``after``, a day qualifies when it is not past the SLA, not in or after
    the freeze window, and not already booked. The latest such day gives the team maximum runway
    while still landing inside the only window that breaches nothing.
    """
    best: str | None = None
    day = after
    for _ in range(60):
        day = day + timedelta(days=1)
        iso = day.isoformat()
        if iso > sla:
            break  # increasing, so no later day can qualify
        if freeze_start is not None and iso >= freeze_start:
            continue
        if iso not in busy:
            best = iso
    return best or (after + timedelta(days=1)).isoformat()


def _reschedule_steps(new_due: str, delta: int) -> list[ExecutionStep]:
    return [
        _step(
            "s1",
            "github",
            "github.update_milestone_due",
            {"milestone": "Launch Rehearsal", "due_on": new_due},
        ),
        _step(
            "s2",
            "outlook",
            "outlook.create_event",
            {"title": f"Launch rehearsal: moved to {new_due}", "start": new_due},
        ),
        _step("s3", "planner", "planner.shift_task_dates", {"delta_days": delta}),
        _step(
            "s4",
            "teams",
            "teams.update_announcement",
            {"channel": "launch", "message": f"Launch rehearsal has moved to {new_due}."},
        ),
    ]


def plan_launch(change: Change, impact: ImpactEvidence) -> ExecutionPlan:
    """Feasible: move the milestone and ripple into calendar, planner, and the announcement.
    When the requested day itself collides with an existing event, the date as posed is refused
    and the next free day is proposed instead — the same ripple, a safer date."""
    new_due = change.due_by or "2026-06-17"
    old_due = _evidence_field(impact, "milestone", "due_on") or "2026-06-10"
    if "schedule.contractual_breach_risk" in impact.tags:
        # A latent cross-system breach the calendar never shows: counter-propose the latest date
        # that honors the SLA, the freeze window, and the go-live buffer — same ripple, safe date.
        cf = next((i for i in impact.items if i.kind == "counterfactual"), None)
        data = cf.data if cf is not None else {}
        sla = str(data.get("sla") or "2026-06-21")
        freeze = data.get("freeze")
        freeze_start = str(freeze.get("start")) if isinstance(freeze, dict) else None
        proposed = _latest_safe_day(_as_day(old_due), sla, freeze_start, _busy_days(impact))
        delta = (_as_day(proposed) - _as_day(old_due)).days
        return ExecutionPlan(
            kind=PlanKind.SAFE_ALTERNATIVE,
            steps=_reschedule_steps(proposed, delta),
            supersedes_request=True,
            rationale=(
                f"The requested {new_due} would breach a contractual SLA / release freeze / "
                f"go-live buffer; propose {proposed} instead — on or before the SLA {sla}, outside "
                "the freeze, preserving the go-live buffer — with the same calendar, schedule, and "
                "announcement ripple."
            ),
        )
    if "schedule.target_date_conflict" in impact.tags:
        clash = _evidence_field(impact, "date_conflict", "title")
        proposed = _next_free_day(_as_day(new_due), _busy_days(impact))
        delta = (_as_day(proposed) - _as_day(old_due)).days
        return ExecutionPlan(
            kind=PlanKind.SAFE_ALTERNATIVE,
            steps=_reschedule_steps(proposed, delta),
            supersedes_request=True,
            rationale=(
                f"The requested {new_due} collides with an existing commitment"
                f"{f' ({clash})' if clash else ''}; propose {proposed} instead, "
                "with the same calendar, schedule, and announcement ripple."
            ),
        )
    delta = (_as_day(new_due) - _as_day(old_due)).days
    return ExecutionPlan(
        kind=PlanKind.FEASIBLE,
        steps=_reschedule_steps(new_due, delta),
        rationale=f"Move the rehearsal to {new_due}; update calendar, schedule, and announcement.",
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
    issue = _blocker_issue(impact) or 42  # fixture blocker only when evidence carried none
    steps = [
        _step("s1", "github", "github.comment_issue", {"issue": issue, "body": comment}),
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


_NOTE_DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")


def plan_meeting_actions(change: Change, impact: ImpactEvidence) -> ExecutionPlan:
    """Feasible: each dated follow-up becomes a tracked task with its owner; the review that was
    proposed without a date gets a calendar slot instead of being lost."""
    item = next((i for i in impact.items if i.kind == "meeting_notes"), None)
    notes = item.data.get("notes") if item is not None else None
    if not isinstance(notes, list):
        return feasible_from_actions(change)

    steps: list[ExecutionStep] = []
    review_proposed = False
    for note in notes:
        if not isinstance(note, dict):
            continue
        text = str(note.get("text", "")).strip()
        found = _NOTE_DATE.search(text)
        if found:
            params: dict[str, object] = {"title": text.rstrip("."), "due": found.group(1)}
            author = str(note.get("author", ""))
            if author:
                params["assignee"] = author
            steps.append(_step(f"s{len(steps) + 1}", "planner", "planner.create_task", params))
        elif "review" in text.lower():
            review_proposed = True
    if review_proposed:
        steps.append(
            _step(
                f"s{len(steps) + 1}",
                "outlook",
                "outlook.create_event",
                {"title": "Progress review", "start": "2026-06-15"},
            )
        )
    if not steps:
        return feasible_from_actions(change)
    return ExecutionPlan(
        kind=PlanKind.FEASIBLE,
        steps=steps,
        rationale=(
            "Track each spoken follow-up as a task with its owner and due date; "
            "schedule the review that was proposed without one."
        ),
    )


def _evidence_count(impact: ImpactEvidence, kind: str, field: str) -> int:
    item = next((i for i in impact.items if i.kind == kind), None)
    value = item.data.get(field) if item is not None else None
    return len(value) if isinstance(value, list) else 0


def plan_weekly_report(change: Change, impact: ImpactEvidence) -> ExecutionPlan:
    """Feasible: compose the report from the gathered evidence and post it once to the channel."""
    closed = _evidence_count(impact, "closed_issues", "issues")
    tasks = _evidence_count(impact, "tasks", "tasks")
    meetings = _evidence_count(impact, "calendar", "events")
    message = (
        f"Weekly report — {closed} issue(s) closed, {tasks} task(s) tracked, "
        f"{meetings} meeting(s) held. Full detail is in the trial's audit record."
    )
    return ExecutionPlan(
        kind=PlanKind.FEASIBLE,
        steps=[
            _step("s1", "teams", "teams.post_message", {"channel": "project-x", "message": message})
        ],
        rationale="Aggregate the week's activity once and post it to the project channel.",
    )


PLANNERS = {
    "launch": plan_launch,
    "sso-ga": plan_sso_ga,
    "project-access": plan_project_access,
    "meeting-actions": plan_meeting_actions,
    "weekly-report": plan_weekly_report,
}
