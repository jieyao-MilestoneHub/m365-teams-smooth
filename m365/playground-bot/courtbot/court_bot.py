"""CourtBot — the thin surface that maps Bot Framework turns to the court engine.

Single responsibility: translate an incoming activity into a ``CourtService`` call and render the
result with the existing card builders. No risk, quorum, planning, or persistence logic lives here —
that is the engine's job. Dependencies (the service and the two card builders) are injected so the
mapping is unit-tested against fakes.

Turn routing:
  * a verdict button (Adaptive Card ``Action.Submit``) arrives as a message whose ``value`` carries
    ``{thread_id, verdict_type, selected_plan}`` -> resume the run, post the verdict-result card;
  * any other text -> open a new trial, post the Change Court card.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from app.domain import PlanKind, RunMode, VerdictType
from app.mcp.cards import build_change_court_card, build_verdict_result_card
from app.services.court_service import CourtService
from botbuilder.core import ActivityHandler, CardFactory, MessageFactory, TurnContext
from botbuilder.schema import ChannelAccount

Card = dict[str, object]
RequestCardBuilder = Callable[[str, Any], Card]
ResultCardBuilder = Callable[..., Card]

WELCOME = (
    "Put a risky decision on trial. Type a change request — for example:\n\n"
    "*promise Customer A that SSO is GA by 2026-06-17*"
)


def _text_card(message: str) -> Card:
    """A minimal Adaptive Card carrying a single line of guidance (prompts and errors)."""
    return {
        "type": "AdaptiveCard",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.5",
        "body": [{"type": "TextBlock", "text": message, "wrap": True}],
    }


class CourtBot(ActivityHandler):  # type: ignore[misc]  # SDK base is untyped (Any) under strict
    """Renders the Change Court card and resumes runs from verdict buttons, in the Playground."""

    def __init__(
        self,
        service: CourtService,
        *,
        request_card: RequestCardBuilder = build_change_court_card,
        result_card: ResultCardBuilder = build_verdict_result_card,
    ) -> None:
        self._service = service
        self._request_card = request_card
        self._result_card = result_card

    def respond(self, *, text: str | None, value: Mapping[str, Any] | None) -> Card:
        """Map one turn to a card. Pure (no I/O beyond the service) so it is unit-testable."""
        if value and "thread_id" in value:
            return self._on_verdict(value)
        if text and text.strip():
            return self._on_request(text.strip())
        return _text_card(WELCOME)

    def _on_request(self, raw_request: str) -> Card:
        summary = self._service.submit_change(
            raw_request, source="playground", run_mode=RunMode.DRY_RUN
        )
        trial = self._service.get_trial(summary.thread_id)
        if trial is None:
            return _text_card("Could not open a trial for that request. Please rephrase it.")
        return self._request_card(summary.thread_id, trial)

    def _on_verdict(self, value: Mapping[str, Any]) -> Card:
        thread_id = str(value["thread_id"])
        try:
            verdict_type = VerdictType(value["verdict_type"])
            selected_plan = PlanKind(value.get("selected_plan", PlanKind.FEASIBLE.value))
        except (KeyError, ValueError):
            return _text_card("That verdict is not recognized.")
        result = self._service.cast_verdict(
            thread_id, verdict_type, selected_plan=selected_plan, actor="playground"
        )
        trial = self._service.get_trial(thread_id)
        if trial is None:
            return _text_card(f"Verdict recorded ({result.status}), but the trial is unavailable.")
        return self._result_card(trial, status=result.status, audit_id=result.audit_id)

    async def on_message_activity(self, turn_context: TurnContext) -> None:
        activity = turn_context.activity
        card = self.respond(text=activity.text, value=activity.value)
        await turn_context.send_activity(MessageFactory.attachment(CardFactory.adaptive_card(card)))

    async def on_members_added_activity(
        self, members_added: list[ChannelAccount], turn_context: TurnContext
    ) -> None:
        recipient_id = turn_context.activity.recipient.id
        for member in members_added:
            if member.id != recipient_id:
                await turn_context.send_activity(
                    MessageFactory.attachment(CardFactory.adaptive_card(_text_card(WELCOME)))
                )
