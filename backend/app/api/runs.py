"""Read-only run inspection: the pipeline run page and its poll endpoint.

A thin façade — the router only verifies the signed link token and delegates to the service.
Access model: the page is gated by a per-thread HMAC token minted with the Change Court card's
deep link; with no ``RUN_LINK_SECRET`` configured the surface is disabled and 404s (an
unverifiable endpoint advertises nothing). The page renders data and exposes no decision action —
verdicts stay on the Adaptive Card.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app.api.deps import get_court_service
from app.domain.errors import NotFoundError
from app.services.court_service import CourtService
from app.services.dto import RunView

router = APIRouter(tags=["runs"])

_STATIC_DIR = Path(__file__).parent / "static"

# The token travels in the URL; keep it out of referrers and crawlers.
_PAGE_HEADERS = {"Referrer-Policy": "no-referrer", "X-Robots-Tag": "noindex"}


def _authorize(service: CourtService, thread_id: str, token: str) -> None:
    if not service.run_page_enabled():
        raise NotFoundError("run page is not enabled")  # fail closed as 404, not 401
    if not service.verify_run_token(thread_id, token):
        raise HTTPException(status_code=401, detail="invalid or missing run link token")


@router.get("/runs/{thread_id}", include_in_schema=False)
async def run_page(
    thread_id: str,
    service: Annotated[CourtService, Depends(get_court_service)],
    t: str = "",
) -> FileResponse:
    """Serve the static run page; the page itself polls the events endpoint below."""
    _authorize(service, thread_id, t)
    return FileResponse(_STATIC_DIR / "run.html", headers=_PAGE_HEADERS)


@router.get("/api/runs/{thread_id}/events")
async def run_events(
    thread_id: str,
    service: Annotated[CourtService, Depends(get_court_service)],
    t: str = "",
    after: int = 0,
) -> RunView:
    """Incremental poll: events past ``after`` plus the current trial view."""
    _authorize(service, thread_id, t)
    return service.get_run_view(thread_id, after_seq=after)
