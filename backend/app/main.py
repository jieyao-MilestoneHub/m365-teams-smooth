"""FastAPI application factory.

Routers (REST health) and the MCP server mount onto this app as later phases land.
The skeleton boots cleanly with no business routes; ``uvicorn app.main:app`` serves it.
"""

from __future__ import annotations

from fastapi import FastAPI

from app import __version__
from app.api.health import router as health_router
from app.config import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build and configure the FastAPI application."""
    settings = settings or Settings()
    app = FastAPI(title="AI Change Court", version=__version__)
    app.state.settings = settings
    app.include_router(health_router)
    return app


app = create_app()
