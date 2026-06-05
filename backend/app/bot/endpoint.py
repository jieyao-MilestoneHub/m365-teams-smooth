"""The bot's HTTP edge: ``POST /api/messages`` on the backend's FastAPI process.

A thin transport shim — Bot Framework auth and turn dispatch belong to the ``CloudAdapter``; the
mapping to the court engine belongs to :class:`~app.bot.court_bot.CourtBot`. Hosting the endpoint
in the same process as the MCP server is deliberate: both surfaces share one in-process
``CourtService`` (one database), so a trial opened in Copilot Chat is approvable from the bot's
buttons and vice versa.

With an empty ``BOT_APP_ID`` the adapter authenticates anonymously, which is what the local
Microsoft 365 Agents Playground / Emulator expects; deployed behind Azure Bot Service the
``BOT_APP_*`` settings carry the bot app registration.
"""

from __future__ import annotations

from botbuilder.core.serializer_helper import serializer_helper
from botbuilder.integration.aiohttp import (
    CloudAdapter,
    ConfigurationBotFrameworkAuthentication,
)
from botbuilder.schema import Activity
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from msrest.serialization import Model

from app.bot.court_bot import CourtBot
from app.config import Settings


class _AdapterConfig:
    """Bot Framework credential configuration, read from settings (empty -> anonymous)."""

    def __init__(self, settings: Settings) -> None:
        self.APP_ID = settings.bot_app_id
        self.APP_PASSWORD = settings.bot_app_password
        self.APP_TYPE = settings.bot_app_type
        self.APP_TENANTID = settings.bot_app_tenant_id


def build_bot_adapter(settings: Settings) -> CloudAdapter:
    """The Bot Framework adapter for both reactive turns and proactive sends."""
    return CloudAdapter(ConfigurationBotFrameworkAuthentication(_AdapterConfig(settings)))


def build_bot_router(bot: CourtBot, adapter: CloudAdapter) -> APIRouter:
    """Mount the Bot Framework messaging endpoint over the shared bot handler."""
    router = APIRouter()

    @router.post("/api/messages")
    async def messages(request: Request) -> Response:
        activity = Activity().deserialize(await request.json())
        if not activity.type:
            return Response(status_code=400)
        auth_header = request.headers.get("Authorization", "")
        try:
            invoke_response = await adapter.process_activity(auth_header, activity, bot.on_turn)
        except PermissionError:
            return Response(status_code=401)
        if invoke_response is not None:
            # Invoke activities (Action.Execute) answer through the HTTP response body — this is
            # how the refreshed card replaces the one the user acted on. The handler usually
            # pre-serializes the body; serialize only what is still an SDK model.
            body = invoke_response.body
            content = serializer_helper(body) if isinstance(body, Model) else body
            return JSONResponse(content=content, status_code=invoke_response.status)
        return Response(status_code=201)

    return router
