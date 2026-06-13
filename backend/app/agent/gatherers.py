"""Per-trial impact gatherers: read capabilities → evidence items + the tags policy matches.

Each gatherer reads only through the registry's adapters (never an SDK) and emits the evidence and
tags for one trial subject. They are registered in ``GATHERERS`` and injected into the impact node.
"""

from __future__ import annotations

import logging
from datetime import date

from app.agent.nodes.impact import Gatherer
from app.agent.policy_rules.packs import (
    CUSTOMER_PROMISE,
    LAUNCH_SLIP,
    MEETING_ACTIONS,
    VENDOR_ACCESS,
    WEEKLY_REPORT,
)
from app.domain import Change, EvidenceItem, GroundedFact, ImpactEvidence
from app.domain.errors import IntegrationError
from app.ports.integration import ReadQuery
from app.ports.knowledge import KnowledgePort
from app.ports.registry import IntegrationRegistry

logger = logging.getLogger(__name__)


def _as_day(value: str) -> date:
    """The calendar day of an ISO date or timestamp (live evidence may carry a full timestamp)."""
    return date.fromisoformat(value[:10])


def _ground(knowledge: KnowledgePort, query: str, errors: list[str]) -> list[GroundedFact]:
    """Best-effort grounding: a knowledge-provider failure costs the citations, not the trial.

    Mirrors the impact node's guard so a gatherer never aborts on an unreachable knowledge base
    (e.g. an expired credential or a transient outage) — the deterministic evidence still stands,
    only its governance citations are absent.
    """
    try:
        return knowledge.ground(query)
    except Exception as exc:  # noqa: BLE001 — any provider failure becomes evidence-level
        logger.warning("knowledge grounding unavailable: %s", exc)
        errors.append(f"knowledge grounding unavailable: {exc}")
        return []


def _read(
    registry: IntegrationRegistry,
    system: str,
    capability: str,
    errors: list[str],
    **params: object,
) -> dict[str, object]:
    adapter = registry.get(system)
    if adapter is None:
        return {}
    try:
        return adapter.read(ReadQuery(capability=capability, params=params)).data
    except IntegrationError as exc:
        # A configured real evidence source that FAILS must not silently under-inform the decision —
        # a dropped read can withhold a risk tag (no milestone read → no milestone_move → lower
        # risk). Log and re-raise so the trial fails loudly rather than producing a quietly
        # under-risked result. Mocks never raise, so offline/CI runs are unaffected; the LLM's
        # additive enrichment reads keep degrading gracefully in the agentic gatherer.
        logger.warning("impact read failed on %s.%s: %s", system, capability, exc)
        raise


# The downstream ripple of a launch move: collapsed into one reader-facing driver, not four.
_RIPPLE_TAGS = frozenset(
    {
        "schedule.milestone_move",
        "schedule.calendar_conflict",
        "schedule.planner_shift",
        "comms.pending_announcement",
    }
)


def gather_launch(
    change: Change,
    registry: IntegrationRegistry,
    knowledge: KnowledgePort,
    errors: list[str],
) -> ImpactEvidence:
    """Launch Slip: a milestone move ripples into calendar, planner, and a pending announcement."""
    items: list[EvidenceItem] = []
    tags: list[str] = []

    milestone = _read(
        registry, "github", "github.read_milestone", errors, milestone="Launch Rehearsal"
    )
    if milestone:
        items.append(
            EvidenceItem(
                system="github",
                kind="milestone",
                summary=(
                    f"Milestone '{milestone.get('title')}' currently due {milestone.get('due_on')}"
                ),
                data=milestone,
            )
        )
        tags.append("schedule.milestone_move")

    events = _read(registry, "outlook", "outlook.read_events", errors).get("events", [])
    if isinstance(events, list) and events:
        items.append(
            EvidenceItem(
                system="outlook",
                kind="calendar",
                summary="Calendar events near the new date",
                data={"events": events},
            )
        )
        tags.append("schedule.calendar_conflict")
        # The requested day itself colliding with an existing event is graver than nearby
        # busyness: the date as posed cannot stand, and the Defender must counter-propose.
        clash = next(
            (
                e
                for e in events
                if change.due_by and str(e.get("start", ""))[:10] == change.due_by
            ),
            None,
        )
        if clash is not None:
            items.append(
                EvidenceItem(
                    system="outlook",
                    kind="date_conflict",
                    summary=(
                        f"The requested date {change.due_by} collides with "
                        f"'{clash.get('title')}'"
                    ),
                    data={"event": clash, "title": clash.get("title")},
                    severity="high",
                    grounded=_ground(knowledge, LAUNCH_SLIP.grounding_query, errors),
                )
            )
            tags.append("schedule.target_date_conflict")

    tasks = _read(registry, "planner", "planner.read_tasks", errors).get("tasks", [])
    if isinstance(tasks, list) and tasks:
        items.append(
            EvidenceItem(
                system="planner",
                kind="tasks",
                summary=f"{len(tasks)} planner task(s) must shift",
                data={"tasks": tasks},
            )
        )
        tags.append("schedule.planner_shift")

    announcement = _read(registry, "teams", "teams.read_announcement", errors, channel="launch")
    if announcement.get("exists"):
        items.append(
            EvidenceItem(
                system="teams",
                kind="announcement",
                summary="A pending announcement references the original date",
                data=announcement,
            )
        )
        tags.append("comms.pending_announcement")

    drivers: list[str] = []
    _derive_contractual_breach(change, registry, knowledge, errors, items, tags, drivers)
    if "schedule.target_date_conflict" in tags:
        drivers.append("Requested date conflict")
    # The milestone/calendar/planner/announcement ripple is one story to an approver, not four.
    if _RIPPLE_TAGS.intersection(tags):
        drivers.append("Downstream schedule updates")
    return ImpactEvidence(items=items, tags=tags, drivers=drivers)


def _derive_contractual_breach(
    change: Change,
    registry: IntegrationRegistry,
    knowledge: KnowledgePort,
    errors: list[str],
    items: list[EvidenceItem],
    tags: list[str],
    drivers: list[str],
) -> None:
    """Cross-reference three systems to catch a breach no single one reveals.

    A target date can be free on the calendar yet still: fall past a contractual launch-readiness
    SLA (CRM), land inside a published release-freeze window (SharePoint), or compress a dependent
    milestone's buffer (GitHub). Each fact lives in a different system; only the *conjunction*
    (>=2 independent constraints) is a hard breach, so the derived unsafe tag fires only then — a
    human eyeballing one system would have approved it.

    Each constraint that fires also contributes a short reader-facing ``driver`` (parallel to its
    detailed ``reason``), so the comment can name the breach's parts without restating the prose.
    """
    target = change.due_by
    if not target:
        return
    reasons: list[str] = []
    breach_drivers: list[str] = []

    contract = _read(registry, "crm", "crm.read_contract", errors, account="Customer A")
    sla = contract.get("launch_readiness_sla")
    if isinstance(sla, str) and target > sla:
        clause = contract.get("clause_id")
        reasons.append(f"past the launch-readiness SLA {sla} (contract clause {clause})")
        breach_drivers.append("Contract cut-off breach")

    sp_data = _read(registry, "sharepoint", "sharepoint.read_change_calendar", errors)
    freezes = sp_data.get("freezes")
    freeze = None
    if isinstance(freezes, list):
        freeze = next(
            (
                f
                for f in freezes
                if isinstance(f, dict)
                and str(f.get("start", "")) <= target <= str(f.get("end", ""))
            ),
            None,
        )
    if freeze is not None:
        reasons.append(f"inside the release freeze {freeze.get('start')}..{freeze.get('end')}")
        breach_drivers.append("Release-freeze window")

    gh_data = _read(
        registry,
        "github",
        "github.read_milestone_dependencies",
        errors,
        milestone="Launch Rehearsal",
    )
    deps = gh_data.get("dependents")
    go_live = None
    if isinstance(deps, list):
        for dep in deps:
            if not isinstance(dep, dict):
                continue
            buffer_days = dep.get("required_buffer_days")
            due = dep.get("due_on")
            if (
                isinstance(buffer_days, int)
                and isinstance(due, str)
                and (_as_day(due) - _as_day(target)).days < buffer_days
            ):
                go_live = dep
                reasons.append(
                    f"compresses the '{dep.get('milestone')}' buffer below "
                    f"{buffer_days} days before go-live {due}"
                )
                breach_drivers.append("Customer go-live buffer")

    if len(reasons) >= 2:
        drivers.extend(breach_drivers)
        items.append(
            EvidenceItem(
                system="derived",
                kind="counterfactual",
                summary=(
                    f"Had {target} been approved as requested it would have: "
                    + "; ".join(reasons)
                    + f". First breach date: {target}."
                ),
                data={
                    "reasons": reasons,
                    "target_date": target,
                    "sla": sla,
                    "freeze": freeze,
                    "go_live": go_live,
                },
                severity="high",
                # Ground on the launch phrase tuned to rank the change-management policy first
                # (its "impact assessment" section covers contractual and downstream implications).
                grounded=_ground(knowledge, LAUNCH_SLIP.grounding_query, errors),
            )
        )
        tags.append("schedule.contractual_breach_risk")


def gather_sso_ga(
    change: Change,
    registry: IntegrationRegistry,
    knowledge: KnowledgePort,
    errors: list[str],
) -> ImpactEvidence:
    """Customer Promise: open blockers, renewal value, and a security review after the date."""
    items: list[EvidenceItem] = []
    tags: list[str] = []

    blockers = _read(registry, "github", "github.read_blocking_issues", errors).get("issues", [])
    if isinstance(blockers, list) and blockers:
        items.append(
            EvidenceItem(
                system="github",
                kind="blockers",
                summary=f"{len(blockers)} open blocking issue(s)",
                data={"issues": blockers},
            )
        )
        tags.append("github.blocking_issues_open")

    account = _read(registry, "crm", "crm.read_account", errors, account="Customer A")
    renewal_value = account.get("renewal_value", 0)
    if isinstance(renewal_value, int) and renewal_value > 0:
        items.append(
            EvidenceItem(
                system="crm",
                kind="renewal",
                summary=f"Renewal value {renewal_value} due {account.get('renewal_date')}",
                data=account,
            )
        )
        tags.append("crm.renewal_at_risk")

    review = _read(registry, "outlook", "outlook.read_security_review", errors, subject="SSO")
    review_date = review.get("review_date")
    if isinstance(review_date, str) and change.due_by and review_date > change.due_by:
        items.append(
            EvidenceItem(
                system="outlook",
                kind="security_review",
                summary=f"Security review on {review_date} is after the promised {change.due_by}",
                data=review,
                severity="high",
                grounded=_ground(knowledge, CUSTOMER_PROMISE.grounding_query, errors),
            )
        )
        tags.append("security.review_after_due_date")

    return ImpactEvidence(items=items, tags=tags)


def gather_project_access(
    change: Change,
    registry: IntegrationRegistry,
    knowledge: KnowledgePort,
    errors: list[str],
) -> ImpactEvidence:
    """Vendor Access: the request is undated and over-broad, and may touch customer data."""
    items: list[EvidenceItem] = []
    tags: list[str] = []

    action = next((a for a in change.requested_actions if a.system == "sharepoint"), None)
    path = str(action.params.get("path", "/ProjectX")) if action else "/ProjectX"

    if action is not None and "expiry" not in action.params:
        items.append(
            EvidenceItem(
                system="request",
                kind="duration",
                summary="Requested access has no end date ('until done')",
            )
        )
        tags.append("access.ambiguous_duration")

    if path.count("/") <= 1:  # e.g. "/ProjectX" — a whole project area, not a single folder
        items.append(
            EvidenceItem(
                system="request",
                kind="scope",
                summary=f"Requested scope '{path}' is broader than necessary",
            )
        )
        tags.append("access.overbroad_scope")

    folder = _read(registry, "sharepoint", "sharepoint.read_folder", errors, path=path)
    if folder.get("contains_customer_data"):
        items.append(
            EvidenceItem(
                system="sharepoint",
                kind="data",
                summary=f"'{path}' holds customer data",
                data=folder,
                severity="high",
                grounded=_ground(knowledge, VENDOR_ACCESS.grounding_query, errors),
            )
        )
        tags.append("data.customer_data_present")

    return ImpactEvidence(items=items, tags=tags)


def gather_meeting_actions(
    change: Change,
    registry: IntegrationRegistry,
    knowledge: KnowledgePort,
    errors: list[str],
) -> ImpactEvidence:
    """Meeting follow-ups: the spoken commitments a discussion left behind, and the calendar."""
    items: list[EvidenceItem] = []
    tags: list[str] = []

    notes = _read(registry, "teams", "teams.read_meeting_notes", errors, channel="standup").get(
        "notes", []
    )
    if isinstance(notes, list) and notes:
        items.append(
            EvidenceItem(
                system="teams",
                kind="meeting_notes",
                summary=f"{len(notes)} spoken follow-up(s) in the standup discussion",
                data={"notes": notes},
                grounded=_ground(knowledge, MEETING_ACTIONS.grounding_query, errors),
            )
        )
        tags.append("meeting.action_items_found")

    events = _read(registry, "outlook", "outlook.read_events", errors).get("events", [])
    if isinstance(events, list) and events:
        items.append(
            EvidenceItem(
                system="outlook",
                kind="calendar",
                summary="Calendar events near the proposed review slot",
                data={"events": events},
            )
        )

    return ImpactEvidence(items=items, tags=tags)


def gather_weekly_report(
    change: Change,
    registry: IntegrationRegistry,
    knowledge: KnowledgePort,
    errors: list[str],
) -> ImpactEvidence:
    """Weekly report: the recent activity scattered across systems, collected once."""
    items: list[EvidenceItem] = []
    tags: list[str] = []

    closed = _read(registry, "github", "github.read_closed_issues", errors).get("issues", [])
    if isinstance(closed, list) and closed:
        items.append(
            EvidenceItem(
                system="github",
                kind="closed_issues",
                summary=f"{len(closed)} issue(s) closed recently",
                data={"issues": closed},
                grounded=_ground(knowledge, WEEKLY_REPORT.grounding_query, errors),
            )
        )
        tags.append("report.activity_collected")

    tasks = _read(registry, "planner", "planner.read_tasks", errors).get("tasks", [])
    if isinstance(tasks, list) and tasks:
        items.append(
            EvidenceItem(
                system="planner",
                kind="tasks",
                summary=f"{len(tasks)} task(s) tracked this week",
                data={"tasks": tasks},
            )
        )

    events = _read(registry, "outlook", "outlook.read_events", errors).get("events", [])
    if isinstance(events, list) and events:
        items.append(
            EvidenceItem(
                system="outlook",
                kind="calendar",
                summary=f"{len(events)} meeting(s) on the calendar",
                data={"events": events},
            )
        )

    return ImpactEvidence(items=items, tags=tags)


def gather_nothing(
    change: Change,
    registry: IntegrationRegistry,
    knowledge: KnowledgePort,
    errors: list[str],
) -> ImpactEvidence:
    """The empty deterministic core for subjects with no registered gatherer.

    The generic agentic gatherer wraps this: the LLM selects every read, and the impact node's
    knowledge grounding still applies. Offline it contributes nothing, by design.
    """
    return ImpactEvidence()


GATHERERS: dict[str, Gatherer] = {
    "launch": gather_launch,
    "sso-ga": gather_sso_ga,
    "project-access": gather_project_access,
    "meeting-actions": gather_meeting_actions,
    "weekly-report": gather_weekly_report,
}
