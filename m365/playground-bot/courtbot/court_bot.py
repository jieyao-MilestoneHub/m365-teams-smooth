"""CourtBot — the thin surface that maps Bot Framework turns to the court engine.

Single responsibility: translate an incoming activity into a ``CourtService`` call and render the
result with the existing card builders. No risk, quorum, planning, or persistence logic lives here —
that is the engine's job. Dependencies (the service and the two card builders) are injected so the
mapping is unit-tested against fakes.

Turn routing:
  * an approval button (``value.tool`` of send_for_approval / withdraw_change / decide) -> the
    matching identity-aware service call, re-rendering the trial in its new phase;
  * a verdict button (Adaptive Card ``Action.Submit``) arrives as a message whose ``value`` carries
    ``{thread_id, verdict_type, selected_plan}`` -> resume the run, post the verdict-result card;
  * the text command ``queue`` -> the caller's pending-approvals list;
  * any other text -> open a new trial, post the Change Court card.

The actor is derived from the activity sender, so the Playground's user switcher exercises the
two-identity flow (requester sends, a different user approves) against the real engine.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable, Mapping
from typing import Any

from app.domain import PlanKind, RunMode, VerdictType
from app.domain.errors import ChangeCourtError
from app.domain.principal import Principal
from app.mcp.cards import build_change_court_card, build_verdict_result_card
from app.services.court_service import CourtService
from botbuilder.core import ActivityHandler, CardFactory, MessageFactory, TurnContext
from botbuilder.schema import ChannelAccount

Card = dict[str, object]
RequestCardBuilder = Callable[..., Card]
ResultCardBuilder = Callable[..., Card]

WELCOME = (
    "Put a risky decision on trial. Type a change request — for example:\n\n"
    "*promise Customer A that SSO is GA by 2026-06-17*\n\n"
    "Type *queue* to see trials awaiting your approval."
)

_QUEUE_COMMANDS = {"queue", "/queue", "pending"}
_APPROVAL_TOOLS = {"send_for_approval", "withdraw_change", "decide"}


def _principal(account: ChannelAccount | None) -> Principal | None:
    """The sender as a Principal. Real Teams supplies the Entra object id; the Playground has only
    the channel account id, which still distinguishes its switchable users."""
    if account is None:
        return None
    oid = getattr(account, "aad_object_id", "") or getattr(account, "id", "") or ""
    name = getattr(account, "name", "") or ""
    if not (oid or name):
        return None
    return Principal(oid=oid, upn=name, display_name=name)

# Bounded memory of processed activity ids: enough to absorb channel redeliveries within a
# Playground session without growing unbounded across long-running processes.
_SEEN_ACTIVITY_CAPACITY = 256


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
        # LRU of activity ids already answered — the channel can redeliver the same activity
        # (observed with Action.Submit in the Playground), which would re-send the result card.
        self._seen_activity_ids: OrderedDict[str, None] = OrderedDict()

    def respond(
        self,
        *,
        text: str | None,
        value: Mapping[str, Any] | None,
        actor: Principal | None = None,
    ) -> Card:
        """Map one turn to a card. Pure (no I/O beyond the service) so it is unit-testable."""
        if value and value.get("tool") in _APPROVAL_TOOLS:
            return self._on_action(value, actor)
        if value and value.get("tool") == "open_trial":
            return self._on_open(value)
        if value and "thread_id" in value:
            return self._on_verdict(value)
        if text and text.strip().lower() in _QUEUE_COMMANDS:
            return self._on_queue(actor)
        if text and text.strip():
            return self._on_request(text.strip(), actor)
        return _text_card(WELCOME)

    def _on_request(self, raw_request: str, actor: Principal | None) -> Card:
        summary = self._service.submit_change(
            raw_request, source="playground", run_mode=RunMode.DRY_RUN, requester=actor
        )
        return self._trial_card(summary.thread_id, status=summary.status)

    def _trial_card(self, thread_id: str, *, status: str) -> Card:
        """The Change Court card for a trial in its current phase."""
        trial = self._service.get_trial(thread_id)
        if trial is None:
            return _text_card("Could not open a trial for that request. Please rephrase it.")
        return self._request_card(
            thread_id,
            trial,
            status=status,
            requester_note=self._service.requester_note(thread_id),
        )

    def _on_action(self, value: Mapping[str, Any], actor: Principal | None) -> Card:
        """Route an approval button to its service gate; errors render as guidance, not crashes."""
        if actor is None:
            return _text_card("Could not identify you from this channel; approval needs a sender.")
        thread_id = str(value.get("thread_id", ""))
        tool = value.get("tool")
        note = str(value.get("note", "") or "")
        try:
            if tool == "send_for_approval":
                summary = self._service.send_for_approval(thread_id, actor=actor, note=note)
            elif tool == "withdraw_change":
                summary = self._service.withdraw_change(thread_id, actor=actor)
            else:
                approve = bool(value.get("approve"))
                summary = self._service.decide(
                    thread_id, actor=actor, approve=approve, note=note
                )
        except (ChangeCourtError, ValueError) as exc:
            return _text_card(f"⛔ {exc}")
        if summary.status in {"awaiting_requester_review", "awaiting_approval"}:
            return self._trial_card(thread_id, status=summary.status)
        trial = self._service.get_trial(thread_id)
        if trial is None:
            return _text_card(f"Recorded ({summary.status}), but the trial is unavailable.")
        return self._result_card(trial, status=summary.status, audit_id=None)

    def _on_open(self, value: Mapping[str, Any]) -> Card:
        """Re-render a trial from the queue card in its current phase."""
        thread_id = str(value.get("thread_id", ""))
        status = self._service.get_status(thread_id)
        if status is None:
            return _text_card(f"Unknown trial: {thread_id}")
        return self._trial_card(thread_id, status=status)

    def _on_queue(self, actor: Principal | None) -> Card:
        """The caller's pull queue: trials awaiting an approval they are authorized to give."""
        if actor is None:
            return _text_card("Could not identify you from this channel.")
        pending = self._service.list_pending_approvals(actor)
        if not pending:
            return _text_card("No trials are waiting for your approval.")
        header = {"type": "TextBlock", "text": "Awaiting your approval", "weight": "Bolder"}
        body: list[object] = [header]
        actions: list[object] = []
        for summary in pending:
            body.append(
                {
                    "type": "TextBlock",
                    "text": f"• {summary.thread_id} — risk {summary.risk_level or 'n/a'}",
                    "wrap": True,
                }
            )
            actions.append(
                {
                    "type": "Action.Submit",
                    "title": f"Open {summary.thread_id[:8]}…",
                    "data": {"tool": "open_trial", "thread_id": summary.thread_id},
                }
            )
        return {
            "type": "AdaptiveCard",
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "version": "1.5",
            "body": body,
            "actions": actions,
        }

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

    def _already_handled(self, activity_id: str | None) -> bool:
        """Record ``activity_id`` and report whether it was seen before (None never dedupes)."""
        if not activity_id:
            return False
        if activity_id in self._seen_activity_ids:
            self._seen_activity_ids.move_to_end(activity_id)
            return True
        self._seen_activity_ids[activity_id] = None
        if len(self._seen_activity_ids) > _SEEN_ACTIVITY_CAPACITY:
            self._seen_activity_ids.popitem(last=False)
        return False

    async def on_message_activity(self, turn_context: TurnContext) -> None:
        activity = turn_context.activity
        if self._already_handled(activity.id):
            return  # redelivered activity: the card for this turn was already sent once
        actor = _principal(activity.from_property)
        card = self.respond(text=activity.text, value=activity.value, actor=actor)
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
