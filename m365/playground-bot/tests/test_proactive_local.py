"""The local proactive path: a sent-for-approval trial lands as an actionable card in the
approver's chat, using the real engine, the real SQL conversation store, and the real sender —
only the Bot Framework adapter is faked."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from app.config import Settings
from app.container import build_conversation_store, build_court_service
from app.domain.principal import Principal
from app.services.court_service import CourtService

from courtbot.court_bot import CourtBot
from courtbot.server import wire_proactive

REQUESTER = Principal(oid="oid-req", upn="requester@example.com", display_name="req")
APPROVER = Principal(oid="oid-app", upn="approver@example.com", display_name="app")

_DIRECTORY = "eng_lead:approver@example.com,comms:approver@example.com"
_REFERENCE: dict[str, object] = {
    "channel_id": "playground",
    "service_url": "https://local.playground",
    "conversation": {"id": "conv-approver"},
    "bot": {"id": "bot"},
    "user": {"id": "oid-app"},
}


class _FakeAdapter:
    """Captures proactive sends; runs the callback against a recording turn context."""

    def __init__(self) -> None:
        self.cards: list[dict[str, Any]] = []
        self.conversations: list[str] = []

    async def continue_conversation(
        self, reference: Any, callback: Any, bot_app_id: str | None = None
    ) -> None:
        adapter = self

        class _Turn:
            async def send_activity(self, activity: Any) -> None:
                adapter.cards.append(activity.attachments[0].content)

        self.conversations.append(reference.conversation.id)
        await callback(_Turn())


@pytest.fixture
def engine_settings(tmp_path: Path) -> Settings:
    return Settings(
        force_all_mock=True,
        db_url=f"sqlite:///{tmp_path.as_posix()}/bot.db",
        dry_run_default=True,
        approver_directory=_DIRECTORY,
    )


@pytest.fixture
def service(engine_settings: Settings) -> CourtService:
    return build_court_service(engine_settings)


async def test_send_for_approval_pushes_actionable_card_to_approver_chat(
    engine_settings: Settings, service: CourtService
) -> None:
    adapter = _FakeAdapter()
    store = build_conversation_store(engine_settings)
    sender = wire_proactive(service, adapter, store)
    bot = CourtBot(service, conversation_store=store)
    drainer = asyncio.create_task(sender.run())
    await asyncio.sleep(0)

    # The approver has talked to the bot before, so their reference is on record (SQL-backed).
    store.save(oid=APPROVER.oid, upn=APPROVER.upn, reference=_REFERENCE)

    # Requester opens a trial and sends it for approval — all through the bot's own mapping.
    card = bot.respond(
        text="slip the launch from 2026-06-10 to 2026-06-17", value=None, actor=REQUESTER
    )
    send = next(a for a in card["actions"] if a["data"]["tool"] == "send_for_approval")
    bot.respond(
        text=None, value={**send["data"], "note": "one more week"}, actor=REQUESTER
    )

    await sender.stop()
    await asyncio.wait_for(drainer, timeout=5)

    # The approver's chat received the approval-phase card with native decide buttons.
    assert adapter.conversations == ["conv-approver"]
    pushed = adapter.cards[0]
    assert [a["verb"] for a in pushed["actions"]] == ["decide", "decide"]
    assert "one more week" in str(pushed)


async def test_unreachable_approver_breaks_nothing(
    engine_settings: Settings, service: CourtService
) -> None:
    adapter = _FakeAdapter()
    store = build_conversation_store(engine_settings)
    sender = wire_proactive(service, adapter, store)
    bot = CourtBot(service, conversation_store=store)
    drainer = asyncio.create_task(sender.run())
    await asyncio.sleep(0)

    card = bot.respond(
        text="slip the launch from 2026-06-10 to 2026-06-17", value=None, actor=REQUESTER
    )
    send = next(a for a in card["actions"] if a["data"]["tool"] == "send_for_approval")
    refreshed = bot.respond(
        text=None, value={**send["data"], "note": "ready"}, actor=REQUESTER
    )

    await sender.stop()
    await asyncio.wait_for(drainer, timeout=5)

    # No stored reference: nothing pushed, and the requester's flow still advanced.
    assert adapter.cards == []
    assert [a["verb"] for a in refreshed["actions"]] == ["decide", "decide"]
