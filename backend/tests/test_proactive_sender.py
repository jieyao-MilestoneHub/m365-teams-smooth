"""The proactive sender: thread-safe submit, per-job delivery, failure isolation, clean stop."""

from __future__ import annotations

import asyncio
import threading
from typing import Any

import pytest
from botbuilder.schema import Activity, ChannelAccount, ConversationAccount

from app.bot.proactive import ProactiveJob, ProactiveSender

_REFERENCE: dict[str, object] = {
    "channel_id": "test",
    "service_url": "https://example.test",
    "conversation": {"id": "conv-1"},
    "bot": {"id": "bot"},
    "user": {"id": "user-1"},
}


class _FakeTurnContext:
    """The two members the sender's callbacks touch: the activity and send_activity."""

    def __init__(self, activity: Activity) -> None:
        self.activity = activity
        self.sent: list[Any] = []

    async def send_activity(self, activity: Any) -> None:
        self.sent.append(activity)


class _FakeAdapter:
    """Records continue/create conversation calls and can fail on demand."""

    def __init__(self, *, fail_on: set[str] | None = None) -> None:
        self.delivered: list[tuple[Any, str]] = []
        self.created: list[tuple[str, Any, str | None, str | None]] = []
        self.create_sent: list[Any] = []
        self._fail_on = fail_on or set()

    async def continue_conversation(
        self, reference: Any, callback: Any, bot_app_id: str | None = None
    ) -> None:
        conv_id = reference.conversation.id
        if conv_id in self._fail_on:
            raise RuntimeError("channel unreachable")
        self.delivered.append((reference, bot_app_id or ""))

    async def create_conversation(
        self,
        bot_app_id: str,
        callback: Any = None,
        conversation_parameters: Any = None,
        channel_id: str | None = None,
        service_url: str | None = None,
        audience: str | None = None,
    ) -> None:
        self.created.append((bot_app_id, conversation_parameters, channel_id, service_url))
        # The channel answers with a turn inside the new conversation, like the real connector.
        activity = Activity(
            type="event",
            channel_id=channel_id or "msteams",
            service_url=service_url,
            conversation=ConversationAccount(id="conv-created"),
            recipient=conversation_parameters.bot,
            from_property=conversation_parameters.members[0],
        )
        context = _FakeTurnContext(activity)
        if callback is not None:
            await callback(context)
        self.create_sent.extend(context.sent)


def _job(conv_id: str, thread_id: str = "t1") -> ProactiveJob:
    reference = dict(_REFERENCE)
    reference["conversation"] = {"id": conv_id}
    return ProactiveJob(
        reference=reference,
        card={"type": "AdaptiveCard", "body": []},
        thread_id=thread_id,
    )


async def _run_until_stopped(sender: ProactiveSender, work: Any) -> None:
    drainer = asyncio.create_task(sender.run())
    await asyncio.sleep(0)  # let run() capture the loop before jobs arrive
    await work()
    await sender.stop()
    await asyncio.wait_for(drainer, timeout=5)


async def test_submitted_jobs_are_delivered_in_order() -> None:
    adapter = _FakeAdapter()
    sender = ProactiveSender(adapter, bot_app_id="app-1")

    async def work() -> None:
        sender.submit(_job("conv-a"))
        sender.submit(_job("conv-b"))

    await _run_until_stopped(sender, work)
    assert [r.conversation.id for r, _ in adapter.delivered] == ["conv-a", "conv-b"]
    assert all(app_id == "app-1" for _, app_id in adapter.delivered)


async def test_submit_is_thread_safe_from_a_worker_thread() -> None:
    # The court service runs synchronously (often on a worker thread); submit must cross into
    # the event loop safely.
    adapter = _FakeAdapter()
    sender = ProactiveSender(adapter, bot_app_id="")

    async def work() -> None:
        thread = threading.Thread(target=lambda: sender.submit(_job("conv-thread")))
        thread.start()
        await asyncio.to_thread(thread.join)
        await asyncio.sleep(0.05)  # give the loop a tick to drain

    await _run_until_stopped(sender, work)
    assert [r.conversation.id for r, _ in adapter.delivered] == ["conv-thread"]


async def test_one_failed_delivery_never_stops_the_drainer() -> None:
    adapter = _FakeAdapter(fail_on={"conv-broken"})
    sender = ProactiveSender(adapter, bot_app_id="")

    async def work() -> None:
        sender.submit(_job("conv-broken"))
        sender.submit(_job("conv-ok"))

    await _run_until_stopped(sender, work)
    # The broken delivery is dropped (best-effort); the next one still lands.
    assert [r.conversation.id for r, _ in adapter.delivered] == ["conv-ok"]


async def test_submit_outside_a_running_drainer_raises() -> None:
    sender = ProactiveSender(_FakeAdapter(), bot_app_id="")
    with pytest.raises(RuntimeError):
        sender.submit(_job("conv-early"))


def _create_job(oid: str) -> ProactiveJob:
    return ProactiveJob(
        reference=None,
        card={"type": "AdaptiveCard", "body": []},
        thread_id="t1",
        recipient_oid=oid,
    )


async def test_jobs_without_a_reference_create_the_conversation() -> None:
    adapter = _FakeAdapter()
    saved: list[tuple[str, dict[str, object]]] = []
    sender = ProactiveSender(
        adapter,
        bot_app_id="app-1",
        tenant_id="tid-1",
        service_url="https://smba.test/teams/",
        save_reference=lambda oid, reference: saved.append((oid, reference)),
    )

    async def work() -> None:
        sender.submit(_create_job("oid-approver"))

    await _run_until_stopped(sender, work)
    assert len(adapter.created) == 1
    bot_app_id, parameters, channel_id, service_url = adapter.created[0]
    assert bot_app_id == "app-1"
    assert parameters.members[0].id == "oid-approver"  # the channel resolves the Entra oid
    assert parameters.tenant_id == "tid-1" and parameters.is_group is False
    assert channel_id == "msteams" and service_url == "https://smba.test/teams/"
    assert ChannelAccount(id="28:app-1") == parameters.bot
    assert adapter.create_sent, "the card is delivered in the created conversation's turn"
    # The captured reference is persisted so the next card takes the continue path.
    assert saved and saved[0][0] == "oid-approver"
    conversation = saved[0][1]["conversation"]
    assert isinstance(conversation, dict) and conversation["id"] == "conv-created"


async def test_create_jobs_without_bot_identity_are_dropped() -> None:
    # Anonymous deployments (Playground/Emulator) cannot address users; the job is logged and
    # dropped, never raising into the drainer.
    adapter = _FakeAdapter()
    sender = ProactiveSender(adapter, bot_app_id="", tenant_id="", service_url="")

    async def work() -> None:
        sender.submit(_create_job("oid-approver"))

    await _run_until_stopped(sender, work)
    assert adapter.created == [] and adapter.delivered == []
