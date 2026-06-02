"""Intake node: parse the request into a structured Change and run the hallucination guard.

Parsing is deterministic so the trials are reproducible. The guard validates every requested action
against the registered capabilities; an unsupported action (e.g. "delete the repo") is rejected — it
is recorded as an error and excluded from the change, so it is neither planned nor executed.
"""

from __future__ import annotations

import re

from app.agent.state import CourtState, serialize
from app.domain import Change, ChangeStatus, RequestedAction
from app.domain.errors import CapabilityNotFoundError
from app.ports.registry import IntegrationRegistry

_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _has(text: str, *words: str) -> bool:
    return any(re.search(rf"\b{re.escape(w)}\b", text) for w in words)


def parse_request(raw: str, *, change_id: str) -> Change:
    """Deterministically parse a request into a structured Change for one of the three trials."""
    text = raw.lower()
    dates = _ISO_DATE.findall(raw)
    due_by = dates[-1] if dates else None
    actions: list[RequestedAction] = []
    subject: str | None = None

    if _has(text, "vendor", "guest") or ("access" in text and "project" in text):
        subject = "project-access"
        actions.append(
            RequestedAction(
                system="sharepoint",
                capability_name="sharepoint.grant_folder_permission",
                verb="grant",
                # Deliberately broad and undated — options narrows this to least-privilege.
                params={"path": "/ProjectX", "principal": "vendor@example.com", "role": "write"},
            )
        )
    elif _has(text, "promise", "ga") or "generally available" in text:
        # A commitment, not a single capability; options produces the safe alternative.
        subject = "sso-ga"
    elif _has(text, "launch", "milestone", "slip"):
        subject = "launch"
        actions.append(
            RequestedAction(
                system="github",
                capability_name="github.update_milestone_due",
                verb="update",
                params={"milestone": "Launch", "due_on": due_by},
            )
        )
        if _has(text, "delete") and _has(text, "repo", "repository"):
            actions.append(
                RequestedAction(
                    system="github",
                    capability_name="github.delete_repo",  # unregistered — the guard rejects this
                    verb="delete",
                    params={"repo": "launch"},
                )
            )

    return Change(
        change_id=change_id,
        raw_request=raw,
        subject=subject,
        due_by=due_by,
        requested_actions=actions,
    )


class IntakeNode:
    """Parses the request and rejects any action without a registered capability."""

    def __init__(self, registry: IntegrationRegistry) -> None:
        self._registry = registry

    def __call__(self, state: CourtState) -> CourtState:
        change = parse_request(state["raw_request"], change_id=state["change_id"])
        requested = list(change.requested_actions)
        kept: list[RequestedAction] = []
        errors = list(state.get("errors", []))

        for action in requested:
            adapter = self._registry.get(action.system)
            try:
                if adapter is None:
                    raise CapabilityNotFoundError(f"no adapter for system '{action.system}'")
                adapter.validate(action)
                kept.append(action)
            except CapabilityNotFoundError as exc:
                errors.append(
                    f"rejected unsupported action {action.system}.{action.capability_name}: {exc}"
                )

        change.requested_actions = kept
        blocked = bool(requested) and not kept
        change.status = ChangeStatus.BLOCKED if blocked else ChangeStatus.EVALUATING

        update: CourtState = {
            "change": serialize(change),
            "status": change.status.value,
            "errors": errors,
        }
        return update
