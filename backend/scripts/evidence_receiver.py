"""Reference receiver: lands the court's evidence packet on an existing change ticket.

The evidence webhook (``EvidenceWebhookNotifier``, enabled by ``EVIDENCE_WEBHOOK_URL``) POSTs one
JSON packet per trial event — an ``analyzed`` conclusion or an approval event. This app is the
other end of that seam for a ticket-first workflow: ``POST /evidence`` renders the packet as
markdown and posts it as a comment on a configured GitHub issue — the change ticket the team
already has gains the full impact analysis (risk factors with citations, evidence, the plan or
safer alternative, the run-page link). Swap the ``_post_comment`` call for any ITSM API to adapt
it. The rendering itself lives in ``scripts.evidence_markdown`` so tooling can preview a comment
without any credentials.

Run it next to (or reachable from) the backend and point the webhook at it:

    GITHUB_TOKEN=... GITHUB_REPO=owner/name EVIDENCE_ISSUE=123 \\
        uv run uvicorn scripts.evidence_receiver:app --port 8088
    # backend: EVIDENCE_WEBHOOK_URL=http://<receiver-host>:8088/evidence

Configuration is read at import time and fails fast — a receiver that cannot reach its ticket is
misconfiguration, not a runtime edge case. Delivery stays best-effort end to end: the notifier
raises on a non-2xx from here, and the court treats notification failure as non-fatal.
"""

from __future__ import annotations

import os

import httpx
from fastapi import FastAPI, Response

from scripts.evidence_markdown import render_markdown

__all__ = ["app", "render_markdown"]

_API = "https://api.github.com"


def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(
            f"{name} is required — the receiver posts to one configured GitHub issue "
            "(GITHUB_TOKEN, GITHUB_REPO as owner/name, EVIDENCE_ISSUE as the issue number)"
        )
    return value


_TOKEN = _require_env("GITHUB_TOKEN")
_REPO = _require_env("GITHUB_REPO")
_ISSUE = _require_env("EVIDENCE_ISSUE")

app = FastAPI(title="Change Court evidence receiver")


def _post_comment(body: str) -> None:
    response = httpx.post(
        f"{_API}/repos/{_REPO}/issues/{_ISSUE}/comments",
        json={"body": body},
        headers={
            "Authorization": f"Bearer {_TOKEN}",
            "Accept": "application/vnd.github+json",
        },
        timeout=10.0,
    )
    response.raise_for_status()


@app.post("/evidence")
def receive(packet: dict[str, object], response: Response) -> dict[str, str]:
    """One webhook POST → one issue comment; a GitHub failure surfaces as 502."""
    try:
        _post_comment(render_markdown(packet))
    except httpx.HTTPError as exc:
        response.status_code = 502
        return {"status": "error", "detail": str(exc)}
    return {"status": "posted"}
