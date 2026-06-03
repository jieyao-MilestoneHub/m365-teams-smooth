"""Per-trial impact gatherers: read capabilities → evidence items + the tags policy matches.

Each gatherer reads only through the registry's adapters (never an SDK) and emits the evidence and
tags for one trial subject. They are registered in ``GATHERERS`` and injected into the impact node.
"""

from __future__ import annotations

import logging

from app.agent.nodes.impact import Gatherer
from app.domain import Change, EvidenceItem, ImpactEvidence
from app.domain.errors import IntegrationError
from app.ports.integration import ReadQuery
from app.ports.knowledge import KnowledgePort
from app.ports.registry import IntegrationRegistry

logger = logging.getLogger(__name__)


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
        # A failing read must not abort the impact node: log, record, and skip this source
        # so the remaining evidence still gathers.
        logger.warning("impact read failed on %s.%s: %s", system, capability, exc)
        errors.append(f"impact read failed on {system}.{capability}: {exc}")
        return {}


def gather_launch(
    change: Change,
    registry: IntegrationRegistry,
    knowledge: KnowledgePort,
    errors: list[str],
) -> ImpactEvidence:
    """Launch Slip: a milestone move ripples into calendar, planner, and a pending announcement."""
    items: list[EvidenceItem] = []
    tags: list[str] = []

    milestone = _read(registry, "github", "github.read_milestone", errors, milestone="Launch")
    if milestone:
        items.append(
            EvidenceItem(
                system="github",
                kind="milestone",
                summary=f"Milestone 'Launch' currently due {milestone.get('due_on')}",
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

    return ImpactEvidence(items=items, tags=tags)


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
                grounded=knowledge.ground("SSO GA promise security review"),
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
                grounded=knowledge.ground("vendor access least privilege scope"),
            )
        )
        tags.append("data.customer_data_present")

    return ImpactEvidence(items=items, tags=tags)


GATHERERS: dict[str, Gatherer] = {
    "launch": gather_launch,
    "sso-ga": gather_sso_ga,
    "project-access": gather_project_access,
}
