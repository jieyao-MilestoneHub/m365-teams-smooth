"""FastAPI/MCP dependency wiring: a process-wide CourtService built from settings."""

from __future__ import annotations

from functools import lru_cache

from app.config import Settings
from app.container import build_court_service
from app.services.court_service import CourtService


@lru_cache(maxsize=1)
def get_court_service() -> CourtService:
    """Return the singleton CourtService (built lazily from environment settings)."""
    return build_court_service(Settings())
