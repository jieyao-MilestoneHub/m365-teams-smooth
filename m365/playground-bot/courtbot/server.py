"""aiohttp host for the Change Court bot — a single ``POST /api/messages`` endpoint.

Composition happens here at the edge: the court engine is built fully mocked (``FORCE_ALL_MOCK``,
no credentials) so the bot runs without a Microsoft 365 tenant, and the Bot Framework adapter uses
anonymous credentials so the Microsoft 365 Agents Playground / Emulator can connect locally.

The proactive path runs locally too: conversation references persist in the bot's database, and a
``ProactiveSender`` on the server's event loop pushes the approval card into the approver's chat
when a change is sent for approval — the same wiring the deployed backend uses, so the full
button-driven flow (requester sends, approver's chat receives the actionable card) is exercisable
in the Playground's user switcher.

Run: ``uv run python -m courtbot.server`` (or ``make bot``).
"""

from __future__ import annotations

import asyncio

from aiohttp import web
from aiohttp.web import Request, Response
from app.adapters.notifiers import BotCardNotifier
from app.bot.proactive import ProactiveJob, ProactiveSender
from app.config import Settings
from app.container import build_conversation_store, build_court_service
from app.ports.conversation_store import ConversationStore
from app.services.court_service import CourtService
from botbuilder.core.integration import aiohttp_error_middleware
from botbuilder.integration.aiohttp import (
    CloudAdapter,
    ConfigurationBotFrameworkAuthentication,
)

from courtbot.court_bot import CourtBot
from courtbot.settings import BotSettings


class _AdapterConfig:
    """Anonymous Bot Framework credentials — no tenant app registration for local Playground use."""

    APP_ID = ""
    APP_PASSWORD = ""
    APP_TYPE = "MultiTenant"
    APP_TENANTID = ""


def wire_proactive(
    service: CourtService, adapter: CloudAdapter, store: ConversationStore
) -> ProactiveSender:
    """Attach the bot-chat card channel to ``service`` and return its (not yet running) sender.

    Mirrors the deployed backend's composition: the notifier only enqueues; the returned sender
    must be drained on the event loop (here via the aiohttp startup/cleanup hooks).
    """
    sender = ProactiveSender(adapter, bot_app_id="")
    service.attach_notifier(
        BotCardNotifier(
            conversation_store=store,
            submit_job=lambda reference, card, thread_id: sender.submit(
                ProactiveJob(reference=reference, card=card, thread_id=thread_id)
            ),
            trial_reader=service.get_trial,
            note_reader=service.requester_note,
            status_reader=service.get_status,
        )
    )
    return sender


def create_app(service: CourtService | None = None) -> web.Application:
    """Build the aiohttp app. Inject ``service`` in tests; otherwise a mocked engine is built."""
    settings = BotSettings()
    engine_settings = Settings(
        force_all_mock=True, db_url=settings.db_url, dry_run_default=True
    )
    if service is None:
        service = build_court_service(engine_settings)
    adapter = CloudAdapter(ConfigurationBotFrameworkAuthentication(_AdapterConfig()))
    store = build_conversation_store(engine_settings)
    sender = wire_proactive(service, adapter, store)
    bot = CourtBot(service, conversation_store=store)

    async def messages(req: Request) -> Response:
        # CloudAdapter.process handles the HTTP plumbing; its return type is untyped (Any).
        return await adapter.process(req, bot)  # type: ignore[no-any-return]

    async def _start_sender(app: web.Application) -> None:
        app["proactive_drainer"] = asyncio.create_task(sender.run())

    async def _stop_sender(app: web.Application) -> None:
        await sender.stop()
        await app["proactive_drainer"]

    app = web.Application(middlewares=[aiohttp_error_middleware])
    app.router.add_post("/api/messages", messages)
    app.on_startup.append(_start_sender)
    app.on_cleanup.append(_stop_sender)
    return app


def main() -> None:
    settings = BotSettings()
    web.run_app(create_app(), host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
