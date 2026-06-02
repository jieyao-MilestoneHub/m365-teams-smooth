"""REST health endpoint. This is the only REST surface; trial/audit data is an MCP resource."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app import __version__

router = APIRouter(prefix="/api", tags=["health"])


class HealthResponse(BaseModel):
    """Liveness payload returned by ``GET /api/health``."""

    status: str
    version: str


@router.get("/health")
async def health() -> HealthResponse:
    """Report that the process is up."""
    return HealthResponse(status="healthy", version=__version__)
