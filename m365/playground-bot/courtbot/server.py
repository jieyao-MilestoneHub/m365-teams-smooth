"""aiohttp host for the Change Court bot — a single ``POST /api/messages`` endpoint.

Composition happens here at the edge: the court engine is built fully mocked (``FORCE_ALL_MOCK``,
no credentials) so the bot runs without a Microsoft 365 tenant, and the Bot Framework adapter uses
anonymous credentials so the Microsoft 365 Agents Playground / Emulator can connect locally.

Run: ``uv run python -m courtbot.server`` (or ``make bot``).
"""

from __future__ import annotations

from aiohttp import web
from aiohttp.web import Request, Response
from app.config import Settings
from app.container import build_court_service
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


def create_app(service: CourtService | None = None) -> web.Application:
    """Build the aiohttp app. Inject ``service`` in tests; otherwise a mocked engine is built."""
    settings = BotSettings()
    if service is None:
        service = build_court_service(
            Settings(force_all_mock=True, db_url=settings.db_url, dry_run_default=True)
        )
    bot = CourtBot(service)
    adapter = CloudAdapter(ConfigurationBotFrameworkAuthentication(_AdapterConfig()))

    async def messages(req: Request) -> Response:
        # CloudAdapter.process handles the HTTP plumbing; its return type is untyped (Any).
        return await adapter.process(req, bot)  # type: ignore[no-any-return]

    app = web.Application(middlewares=[aiohttp_error_middleware])
    app.router.add_post("/api/messages", messages)
    return app


def main() -> None:
    settings = BotSettings()
    web.run_app(create_app(), host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
