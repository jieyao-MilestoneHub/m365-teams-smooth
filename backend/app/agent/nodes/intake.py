"""Intake node: turn the request into a structured Change and run the hallucination guard.

Parsing is delegated to a ``RequestParser`` (deterministic by default; LLM-backed when configured),
so intake stays focused on the guard: it validates every requested action against the registered
capabilities; an unsupported action (e.g. "delete the repo") is rejected — recorded as an error and
excluded from the change, so it is neither planned nor executed.
"""

from __future__ import annotations

from app.agent.state import CourtState, bound_errors, serialize
from app.domain import ChangeStatus, RequestedAction
from app.domain.errors import CapabilityNotFoundError
from app.ports.registry import IntegrationRegistry
from app.ports.request_parser import RequestParser


class IntakeNode:
    """Parses the request (via the injected parser) and rejects unregistered actions."""

    def __init__(self, parser: RequestParser, registry: IntegrationRegistry) -> None:
        self._parser = parser
        self._registry = registry

    def __call__(self, state: CourtState) -> CourtState:
        change = self._parser.parse(state["raw_request"], change_id=state["change_id"])
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
            "errors": bound_errors(errors),
        }
        return update
