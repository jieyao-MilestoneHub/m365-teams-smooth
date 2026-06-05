"""The proactive sender: thread-safe submit, per-job delivery, failure isolation, clean stop."""

from __future__ import annotations

import asyncio
import threading
from typing import Any

import pytest

from app.bot.proactive import ProactiveJob, ProactiveSender

_REFERENCE: dict[str, object] = {
    "channel_id": "test",
    "service_url": "https://example.test",
    "conversation": {"id": "conv-1"},
    "bot": {"id": "bot"},
    "user": {"id": "user-1"},
}


class _FakeAdapter:
    """Records continue_conversation calls and can fail on demand."""

    def __init__(self, *, fail_on: set[str] | None = None) -> None:
        self.delivered: list[tuple[Any, str]] = []
        self._fail_on = fail_on or set()

    async def continue_conversation(
        self, reference: Any, callback: Any, bot_app_id: str | None = None
    ) -> None:
        conv_id = reference.conversation.id
        if conv_id in self._fail_on:
            raise RuntimeError("channel unreachable")
        self.delivered.append((reference, bot_app_id or ""))


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
