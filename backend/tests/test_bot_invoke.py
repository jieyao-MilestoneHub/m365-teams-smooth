"""Action.Execute invokes route through the same service gates and refresh the card in place."""

from __future__ import annotations

from typing import Any

import pytest
from botbuilder.core import TurnContext
from botbuilder.schema import (
    Activity,
    AdaptiveCardInvokeValue,
    ChannelAccount,
    ConversationAccount,
)

from app.bot.court_bot import CourtBot, _principal
from app.config import Settings
from app.container import build_court_service
from app.domain import RunMode
from app.domain.principal import Principal
from app.services.court_service import CourtService


def test_principal_keys_on_oid_and_never_fakes_a_upn() -> None:
    # A Teams activity carries the Entra oid + display name but no UPN. The Principal must not
    # label the display name as a UPN — identity has to key on the oid so the conversation store
    # and approver directory match for proactive delivery.
    account = ChannelAccount(id="29:teams-id", name="Alex Approver")
    account.aad_object_id = "c9c71ad1-ee59-4d59-8b28-c725ae0d832e"
    principal = _principal(account)
    assert principal is not None
    assert principal.upn == ""
    assert principal.display_name == "Alex Approver"
    assert principal.key() == "c9c71ad1-ee59-4d59-8b28-c725ae0d832e"

REQUESTER = ChannelAccount(id="user-req", name="requester@example.com")
APPROVER = ChannelAccount(id="user-app", name="approver@example.com")
APPROVER2 = ChannelAccount(id="user-app2", name="approver2@example.com")

_CARD_TYPE = "application/vnd.microsoft.card.adaptive"


def _service(**overrides: Any) -> CourtService:
    return build_court_service(
        Settings(
            force_all_mock=True,
            db_url="sqlite:///:memory:",
            dry_run_default=True,
            **overrides,
        )
    )


class _FakeAdapter:
    async def send_activities(self, context: Any, activities: Any) -> list[Any]:
        return []


def _turn_context(sender: ChannelAccount, activity_id: str = "act-1") -> TurnContext:
    activity = Activity(
        type="invoke",
        name="adaptiveCard/action",
        id=activity_id,
        from_property=sender,
        recipient=ChannelAccount(id="bot"),
        conversation=ConversationAccount(id="conv-1"),
        channel_id="test",
        service_url="https://example.test",
    )
    return TurnContext(_FakeAdapter(), activity)


def _invoke(verb: str, data: dict[str, Any]) -> AdaptiveCardInvokeValue:
    return AdaptiveCardInvokeValue(
        action={"type": "Action.Execute", "verb": verb, "data": {"tool": verb, **data}}
    )


async def test_invoke_routes_through_service_gates_and_refreshes_in_place() -> None:
    # The bot identifies users by their Entra oid (here the channel-account id, since these test
    # accounts carry no aad_object_id), so the directory keys on those same ids.
    directory = "eng_lead:user-app,comms:user-app2"
    service = _service(approver_directory=directory)
    bot = CourtBot(service)

    # Requester opens a trial (message turn) — lands at requester self-review.
    requester = Principal(oid="user-req", upn="requester@example.com", display_name="req")
    summary = service.submit_change(
        "slip the launch from 2026-06-10 to 2026-06-17",
        source="playground",
        run_mode=RunMode.DRY_RUN,
        requester=requester,
    )
    assert summary.status == "awaiting_requester_review"

    # The requester clicks "Send for approval" — the note Input arrives merged into action.data.
    response = await bot.on_adaptive_card_invoke(
        _turn_context(REQUESTER),
        _invoke(
            "send_for_approval", {"thread_id": summary.thread_id, "note": "ship it safely"}
        ),
    )
    assert response.status_code == 200
    assert response.type == _CARD_TYPE
    card = response.value
    assert card["type"] == "AdaptiveCard"
    # The refreshed card is the approval phase: decide buttons, no send button.
    verbs = [a["verb"] for a in card["actions"]]
    assert verbs == ["decide", "decide"]
    assert service.requester_note(summary.thread_id) == "ship it safely"

    # With the "any" policy a single sign-off completes the quorum: the first approver (eng_lead)
    # approves and the terminal result card replaces the approval card in place.
    response = await bot.on_adaptive_card_invoke(
        _turn_context(APPROVER, "act-2"),  # a distinct turn → its own activity id
        _invoke("decide", {"thread_id": summary.thread_id, "approve": True}),
    )
    assert response.status_code == 200
    assert response.type == _CARD_TYPE
    blob = str(response.value)
    assert "⛔" not in blob  # the gate accepted the decision, no guidance card
    assert "Verdict recorded" in blob or "Safe alternative executed" in blob
    assert "actions" not in response.value  # result card is terminal — no further buttons


def test_bot_submit_honors_dry_run_default_for_live_execution() -> None:
    # The bot used to force dry-run; it now follows DRY_RUN_DEFAULT so an operator can run the
    # bot-card flow live. With dry_run_default=False, a bot-opened trial runs in LIVE mode.
    requester = _principal(ChannelAccount(id="user-req", name="Robin"))
    for default, expected in ((True, "dry_run"), (False, "live")):
        service = build_court_service(
            Settings(force_all_mock=True, db_url="sqlite:///:memory:", dry_run_default=default)
        )
        bot = CourtBot(service)
        card = bot.respond(
            text="slip the launch from 2026-06-10 to 2026-06-17", value=None, actor=requester
        )
        actions = card["actions"]
        assert isinstance(actions, list)
        thread_id = str(actions[0]["data"]["thread_id"])
        assert service._runner.state(thread_id).get("run_mode") == expected


async def test_redelivered_invoke_does_not_double_execute(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Teams can re-deliver the same invoke activity (same id). The second delivery must re-render
    # the card read-only, not run send_for_approval again — a double-fire flickers the card and
    # re-appends the SEND.
    service = _service(approver_directory="eng_lead:user-app,comms:user-app2")
    bot = CourtBot(service)
    requester = Principal(oid="user-req", upn="requester@example.com", display_name="req")
    summary = service.submit_change(
        "slip the launch from 2026-06-10 to 2026-06-17",
        source="playground",
        run_mode=RunMode.DRY_RUN,
        requester=requester,
    )

    calls = 0
    original = service.send_for_approval

    def counting(*args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(service, "send_for_approval", counting)

    invoke = _invoke("send_for_approval", {"thread_id": summary.thread_id, "note": "ship it"})
    first = await bot.on_adaptive_card_invoke(_turn_context(REQUESTER), invoke)
    second = await bot.on_adaptive_card_invoke(_turn_context(REQUESTER), invoke)

    assert calls == 1  # the re-delivery did not run the tool again
    # Both deliveries return the approval-phase card; the second is a read-only re-render.
    for resp in (first, second):
        assert resp.status_code == 200
        assert [a["verb"] for a in resp.value["actions"]] == ["decide", "decide"]


async def test_invoke_error_renders_guidance_card_not_crash() -> None:
    service = _service()
    bot = CourtBot(service)
    response = await bot.on_adaptive_card_invoke(
        _turn_context(APPROVER),
        _invoke("decide", {"thread_id": "missing-thread", "approve": True}),
    )
    assert response.status_code == 200
    body_text = str(response.value)
    assert "⛔" in body_text or "Unknown" in body_text
