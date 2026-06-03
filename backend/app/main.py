"""FastAPI application factory.

Routers (REST health) and the MCP server mount onto this app as later phases land.
The skeleton boots cleanly with no business routes; ``uvicorn app.main:app`` serves it.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

from fastapi import FastAPI

from app import __version__
from app.api.health import router as health_router
from app.config import Settings
from app.observability import configure_logging

Lifespan = Callable[[FastAPI], AbstractAsyncContextManager[None]]


def create_app(settings: Settings | None = None, *, lifespan: Lifespan | None = None) -> FastAPI:
    """Build and configure the FastAPI application.

    ``lifespan`` lets a deployment compose extra startup/shutdown (e.g. the MCP session manager)
    without coupling the REST app to those concerns; the health-only app passes none.
    """
    settings = settings or Settings()
    configure_logging(settings)
    app = FastAPI(title="AI Change Court", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.include_router(health_router)
    return app


app = create_app()
