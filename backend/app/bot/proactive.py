"""Proactive card delivery: the seam between the sync court service and the async Bot Framework.

The notifier (sync, called inside a service gate) only enqueues a job; this sender drains the
queue on the server's event loop and pushes the card into the recipient's bot chat via
``continue_conversation``. Delivery is best-effort — a failed send is logged and dropped, mirroring
the service's non-blocking notification contract.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from botbuilder.core import CardFactory, MessageFactory, TurnContext
from botbuilder.core.serializer_helper import deserializer_helper
from botbuilder.schema import ConversationReference

logger = logging.getLogger(__name__)

Card = dict[str, object]


@dataclass(frozen=True)
class ProactiveJob:
    """One card to deliver into the conversation a reference points at."""

    reference: dict[str, object]
    card: Card
    thread_id: str


class ProactiveSender:
    """Drains queued proactive jobs onto the Bot Framework adapter.

    ``submit`` is thread-safe (the service may run on a worker thread); ``run`` must execute on
    the server's event loop, owned by the application lifespan. ``stop`` drains the queue with a
    sentinel so shutdown never abandons an already-enqueued card mid-flight.
    """

    def __init__(self, adapter: Any, *, bot_app_id: str) -> None:
        self._adapter = adapter
        self._bot_app_id = bot_app_id
        self._queue: asyncio.Queue[ProactiveJob | None] = asyncio.Queue()
        self._loop: asyncio.AbstractEventLoop | None = None

    def submit(self, job: ProactiveJob) -> None:
        """Enqueue ``job`` from any thread; raises when the sender is not running."""
        loop = self._loop
        if loop is None or loop.is_closed():
            raise RuntimeError("proactive sender is not running")
        loop.call_soon_threadsafe(self._queue.put_nowait, job)

    async def run(self) -> None:
        """Deliver jobs until ``stop`` enqueues the shutdown sentinel."""
        self._loop = asyncio.get_running_loop()
        while True:
            job = await self._queue.get()
            if job is None:
                return
            try:
                await self._deliver(job)
            except Exception:
                logger.warning(
                    "proactive.failed", extra={"thread_id": job.thread_id}
                )

    async def stop(self) -> None:
        await self._queue.put(None)

    async def _deliver(self, job: ProactiveJob) -> None:
        reference = deserializer_helper(ConversationReference, dict(job.reference))

        async def _send(turn_context: TurnContext) -> None:
            await turn_context.send_activity(
                MessageFactory.attachment(CardFactory.adaptive_card(dict(job.card)))
            )

        await self._adapter.continue_conversation(reference, _send, self._bot_app_id)
