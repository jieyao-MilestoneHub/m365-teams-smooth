"""Deployment ASGI app: the REST health surface, the bot endpoint, and the mounted MCP server.

Composition happens here, at the edge — ``create_app`` stays read-only (health + the run page)
and the MCP server and bot stay façades over the one shared service (so a trial opened over MCP
is approvable from the bot's card buttons). Serve with ``uvicorn app.asgi:app``. The MCP endpoint
is at ``/mcp``; the Bot Framework messaging endpoint is at ``/api/messages``.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import partial

from fastapi import FastAPI
from starlette.types import ASGIApp, Receive, Scope, Send

from app.adapters.notifiers import BotCardNotifier, CompositeNotifier
from app.api.deps import get_court_service
from app.bot.court_bot import CourtBot
from app.bot.endpoint import build_bot_adapter, build_bot_router
from app.bot.proactive import ProactiveJob, ProactiveSender
from app.config import Settings
from app.container import (
    build_conversation_store,
    build_evidence_webhook_notifier,
    build_teams_notifier,
)
from app.main import create_app
from app.mcp.cards import build_change_court_card, build_verdict_result_card
from app.mcp.security import (
    build_auth_settings,
    build_token_verifier,
    build_transport_security,
    protected_resource_metadata,
)
from app.mcp.server import MCP_PATH, build_mcp_server
from app.observability import configure_logging, configure_metrics
from app.ports.notifier import ApprovalNotifier
from app.services.court_service import CourtService


class MountPathNormalizer:
    """Rewrite the bare mount path to the mounted root instead of redirecting.

    Starlette answers ``POST /mcp`` with a 307 to ``/mcp/``; MCP clients (e.g. the Copilot
    plugin runtime) do not follow redirects, so the tool call silently dies. Normalizing the
    path here makes both spellings reach the mounted server directly.
    """

    def __init__(self, app: ASGIApp, mount_path: str) -> None:
        self._app = app
        self._mount_path = mount_path.rstrip("/")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope.get("path") == self._mount_path:
            scope["path"] = self._mount_path + "/"
            scope["raw_path"] = scope["path"].encode("ascii")
        await self._app(scope, receive, send)


def create_full_app(service: CourtService | None = None) -> FastAPI:
    """Build the REST app, the bot endpoint, and the OAuth2-protected MCP server.

    Both interactive surfaces (MCP tools, bot card buttons) close over the same in-process
    ``CourtService``. The notifier is attached late: the bot-chat card channel reads trials
    through the service it notifies for, so it can only be composed once the service exists.
    """
    settings = Settings()
    configure_logging(settings)
    configure_metrics(settings)
    court = service or get_court_service()
    mcp = build_mcp_server(
        court,
        token_verifier=build_token_verifier(settings),
        auth_settings=build_auth_settings(settings),
        transport_security=build_transport_security(settings),
    )

    # Bot surface: the shared handler, its transport adapter, and proactive card delivery.
    # Cards carry the signed run-page deep link; the builders stay pure — the link generator is
    # closed over here, at the composition edge (it is a no-op until RUN_LINK_SECRET is set).
    request_card = partial(build_change_court_card, run_link=court.run_link)
    result_card = partial(build_verdict_result_card, run_link=court.run_link)
    bot_adapter = build_bot_adapter(settings)
    conversation_store = build_conversation_store(settings)
    sender = ProactiveSender(
        bot_adapter,
        bot_app_id=settings.bot_app_id,
        tenant_id=settings.bot_app_tenant_id,
        service_url=settings.bot_service_url,
        # A conversation created by the sender is captured for next time, keyed on the oid the
        # directory hands through — the same key the bot itself stores on contact.
        save_reference=lambda oid, reference: conversation_store.save(
            oid=oid, upn="", reference=reference
        ),
    )
    bot = CourtBot(
        court,
        conversation_store=conversation_store,
        request_card=request_card,
        result_card=result_card,
    )

    channels: list[ApprovalNotifier] = []
    teams_notifier = build_teams_notifier(settings)
    if teams_notifier is not None:
        channels.append(teams_notifier)
    channels.append(
        BotCardNotifier(
            conversation_store=conversation_store,
            submit_job=lambda reference, card, thread_id, recipient: sender.submit(
                ProactiveJob(
                    reference=reference,
                    card=card,
                    thread_id=thread_id,
                    recipient_oid=recipient,
                )
            ),
            trial_reader=court.get_trial,
            note_reader=court.requester_note,
            status_reader=court.get_status,
            request_card=request_card,
            result_card=result_card,
        )
    )
    webhook_notifier = build_evidence_webhook_notifier(
        settings, trial_reader=court.get_trial, run_link=court.run_link
    )
    if webhook_notifier is not None:
        channels.append(webhook_notifier)
    court.attach_notifier(CompositeNotifier(channels))

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        async with mcp.session_manager.run():
            drainer = asyncio.create_task(sender.run())
            try:
                yield
            finally:
                await sender.stop()
                await drainer

    app = create_app(lifespan=lifespan)
    app.include_router(build_bot_router(bot, bot_adapter))

    # RFC 9728: the mounted MCP server's 401 advertises its protected-resource metadata at the
    # ROOT path (``/.well-known/oauth-protected-resource/mcp``), but the SDK only serves it under
    # the ``/mcp`` mount — so the advertised URL 404s and clients can't discover the auth server
    # to start sign-in. Serve the document at the advertised root path too.
    metadata_path = f"/.well-known/oauth-protected-resource{MCP_PATH}"

    @app.get(metadata_path)
    def oauth_protected_resource() -> dict[str, object]:
        return protected_resource_metadata(settings)

    app.mount(MCP_PATH, mcp.streamable_http_app())
    app.add_middleware(MountPathNormalizer, mount_path=MCP_PATH)
    return app


app = create_full_app()
