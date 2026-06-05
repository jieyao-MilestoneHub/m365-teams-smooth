"""CourtBot — the thin surface that maps Bot Framework turns to the court engine.

Single responsibility: translate an incoming activity into a ``CourtService`` call and render the
result with the existing card builders. No risk, quorum, planning, or persistence logic lives here —
that is the engine's job. Dependencies (the service and the two card builders) are injected so the
mapping is unit-tested against fakes.

Turn routing:
  * an ``Action.Execute`` button arrives as an ``adaptiveCard/action`` invoke whose
    ``action.verb``/``action.data`` name the tool -> the matching service call; the response card
    replaces the one acted on **in place** (the buttons disappear, so a second click cannot
    double-act);
  * an ``Action.Submit`` button (legacy/Playground) arrives as a message whose ``value`` carries
    the same ``{tool, thread_id, ...}`` payload -> identical routing through ``respond``;
  * the text command ``queue`` -> the caller's pending-approvals list;
  * any other text -> open a new trial, post the Change Court card.

The actor is derived from the activity sender, so real Teams (Entra object id) and the Playground's
user switcher both exercise the two-identity flow (requester sends, a different user approves).
When a ``ConversationStore`` is injected, every turn records the sender's conversation reference so
the proactive notifier can later deliver approval cards into that user's chat.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable, Mapping
from typing import Any

from botbuilder.core import ActivityHandler, CardFactory, MessageFactory, TurnContext
from botbuilder.core.serializer_helper import serializer_helper
from botbuilder.schema import (
    AdaptiveCardInvokeResponse,
    AdaptiveCardInvokeValue,
    ChannelAccount,
)

from app.domain import PlanKind, VerdictType
from app.domain.errors import ChangeCourtError
from app.domain.principal import Principal
from app.mcp.cards import build_change_court_card, build_verdict_result_card
from app.ports.conversation_store import ConversationStore
from app.services.court_service import CourtService

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

_CARD_CONTENT_TYPE = "application/vnd.microsoft.card.adaptive"


def _principal(account: ChannelAccount | None) -> Principal | None:
    """The sender as a Principal. Real Teams supplies the Entra object id; the Playground has only
    the channel account id, which still distinguishes its switchable users."""
    if account is None:
        return None
    oid = getattr(account, "aad_object_id", "") or getattr(account, "id", "") or ""
    name = getattr(account, "name", "") or ""
    if not (oid or name):
        return None
    # A Teams activity carries the Entra object id and the display name, but NOT the UPN. Leave
    # upn empty rather than mislabel the display name as one — identity then keys on the reliable
    # oid (Principal.key()), which is what the conversation store and the approver directory must
    # match on for proactive card delivery. ``name`` stays as the display label.
    return Principal(oid=oid, upn="", display_name=name)

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
    """Renders the Change Court card and routes its buttons back into the court service."""

    def __init__(
        self,
        service: CourtService,
        *,
        request_card: RequestCardBuilder = build_change_court_card,
        result_card: ResultCardBuilder = build_verdict_result_card,
        conversation_store: ConversationStore | None = None,
    ) -> None:
        self._service = service
        self._request_card = request_card
        self._result_card = result_card
        self._conversation_store = conversation_store
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
        # Honor the deployment's DRY_RUN_DEFAULT instead of forcing dry-run: passing run_mode=None
        # lets the service apply the configured default, so an operator can run the bot-card flow
        # live (real downstream execution) by setting DRY_RUN_DEFAULT=false.
        summary = self._service.submit_change(
            raw_request, source="playground", requester=actor
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
                    "type": "Action.Execute",
                    "title": f"Open {summary.thread_id[:8]}…",
                    "verb": "open_trial",
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

    def _capture_reference(self, turn_context: TurnContext) -> None:
        """Record where the sender can be reached, for proactive approval-card delivery."""
        if self._conversation_store is None:
            return
        account = turn_context.activity.from_property
        actor = _principal(account)
        if actor is None:
            return
        reference = TurnContext.get_conversation_reference(turn_context.activity)
        self._conversation_store.save(
            oid=actor.oid, upn=actor.upn, reference=serializer_helper(reference)
        )

    async def on_message_activity(self, turn_context: TurnContext) -> None:
        activity = turn_context.activity
        self._capture_reference(turn_context)
        if self._already_handled(activity.id):
            return  # redelivered activity: the card for this turn was already sent once
        actor = _principal(activity.from_property)
        card = self.respond(text=activity.text, value=activity.value, actor=actor)
        await turn_context.send_activity(MessageFactory.attachment(CardFactory.adaptive_card(card)))

    async def on_adaptive_card_invoke(
        self, turn_context: TurnContext, invoke_value: AdaptiveCardInvokeValue
    ) -> AdaptiveCardInvokeResponse:
        """An ``Action.Execute`` click: run the named tool, then refresh the card in place."""
        self._capture_reference(turn_context)
        action: Mapping[str, Any] = invoke_value.action or {}
        data = dict(action.get("data") or {})  # the channel merges card Input values in here
        verb = str(action.get("verb") or data.get("tool") or "")
        actor = _principal(turn_context.activity.from_property)
        card = self.respond(text=None, value={**data, "tool": verb}, actor=actor)
        return AdaptiveCardInvokeResponse(
            status_code=200, type=_CARD_CONTENT_TYPE, value=card
        )

    async def on_conversation_update_activity(self, turn_context: TurnContext) -> None:
        self._capture_reference(turn_context)
        await super().on_conversation_update_activity(turn_context)

    async def on_members_added_activity(
        self, members_added: list[ChannelAccount], turn_context: TurnContext
    ) -> None:
        recipient_id = turn_context.activity.recipient.id
        for member in members_added:
            if member.id != recipient_id:
                await turn_context.send_activity(
                    MessageFactory.attachment(CardFactory.adaptive_card(_text_card(WELCOME)))
                )
