"""Proactive card delivery: the seam between the sync court service and the async Bot Framework.

The notifier (sync, called inside a service gate) only enqueues a job; this sender drains the
queue on the server's event loop and pushes the card into the recipient's bot chat via
``continue_conversation``. A job without a stored reference instead **creates** the personal
conversation (valid whenever the app is installed for that user), persists the captured reference
for next time, and delivers in the same turn. Delivery is best-effort — a failed send is logged
and dropped, mirroring the service's non-blocking notification contract.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from botbuilder.core import CardFactory, MessageFactory, TurnContext
from botbuilder.core.serializer_helper import deserializer_helper, serializer_helper
from botbuilder.schema import ChannelAccount, ConversationParameters, ConversationReference

logger = logging.getLogger(__name__)

Card = dict[str, object]
SaveReference = Callable[[str, dict[str, object]], None]


@dataclass(frozen=True)
class ProactiveJob:
    """One card to deliver: into the conversation a reference points at, or — when no reference
    is stored — into a personal conversation created for ``recipient_oid``."""

    reference: dict[str, object] | None
    card: Card
    thread_id: str
    recipient_oid: str = ""


class ProactiveSender:
    """Drains queued proactive jobs onto the Bot Framework adapter.

    ``submit`` is thread-safe (the service may run on a worker thread); ``run`` must execute on
    the server's event loop, owned by the application lifespan. ``stop`` drains the queue with a
    sentinel so shutdown never abandons an already-enqueued card mid-flight.
    """

    def __init__(
        self,
        adapter: Any,
        *,
        bot_app_id: str,
        tenant_id: str = "",
        service_url: str = "",
        save_reference: SaveReference | None = None,
    ) -> None:
        self._adapter = adapter
        self._bot_app_id = bot_app_id
        self._tenant_id = tenant_id
        self._service_url = service_url
        self._save_reference = save_reference
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
            except Exception as exc:
                logger.warning(
                    "proactive.failed",
                    extra={
                        "thread_id": job.thread_id,
                        "identity": job.recipient_oid,
                        "reason": str(exc)[:200],
                    },
                )

    async def stop(self) -> None:
        """Schedule the shutdown sentinel behind any already-submitted jobs.

        The sentinel takes the same ``call_soon_threadsafe`` path as ``submit`` so it cannot jump
        the queue ahead of jobs whose enqueue callbacks are still pending on the loop.
        """
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        loop.call_soon_threadsafe(self._queue.put_nowait, None)

    async def _deliver(self, job: ProactiveJob) -> None:
        if job.reference is None:
            await self._create_and_deliver(job)
            return
        reference = deserializer_helper(ConversationReference, dict(job.reference))

        async def _send(turn_context: TurnContext) -> None:
            await turn_context.send_activity(
                MessageFactory.attachment(CardFactory.adaptive_card(dict(job.card)))
            )

        await self._adapter.continue_conversation(reference, _send, self._bot_app_id)

    async def _create_and_deliver(self, job: ProactiveJob) -> None:
        """Create the recipient's personal conversation, persist its reference, send the card.

        Teams accepts the member's Entra object id whenever the app is installed for that user,
        so a recipient who never messaged the bot is still reachable. Requires the bot's own
        identity (app id + tenant) and a channel service URL; without them the job is logged and
        dropped — the activity-feed toast remains the floor.
        """
        if not (job.recipient_oid and self._bot_app_id and self._tenant_id and self._service_url):
            missing = [
                name
                for name, value in (
                    ("recipient_oid", job.recipient_oid),
                    ("bot_app_id", self._bot_app_id),
                    ("bot_app_tenant_id", self._tenant_id),
                    ("bot_service_url", self._service_url),
                )
                if not value
            ]
            logger.warning(
                "proactive.unaddressable",
                extra={
                    "thread_id": job.thread_id,
                    "identity": job.recipient_oid,
                    "reason": f"cannot create a conversation — missing: {', '.join(missing)}",
                },
            )
            return
        parameters = ConversationParameters(
            is_group=False,
            bot=ChannelAccount(id=f"28:{self._bot_app_id}"),
            members=[ChannelAccount(id=job.recipient_oid)],
            tenant_id=self._tenant_id,
            channel_data={"tenant": {"id": self._tenant_id}},
        )

        async def _send(turn_context: TurnContext) -> None:
            reference = TurnContext.get_conversation_reference(turn_context.activity)
            if self._save_reference is not None:
                self._save_reference(job.recipient_oid, serializer_helper(reference))
            await turn_context.send_activity(
                MessageFactory.attachment(CardFactory.adaptive_card(dict(job.card)))
            )

        await self._adapter.create_conversation(
            self._bot_app_id,
            callback=_send,
            conversation_parameters=parameters,
            channel_id="msteams",
            service_url=self._service_url,
        )
