"""Reference receiver: lands the court's evidence packet on an existing change ticket.

The evidence webhook (``EvidenceWebhookNotifier``, enabled by ``EVIDENCE_WEBHOOK_URL``) POSTs one
JSON packet per approval event. This app is the other end of that seam for a ticket-first
workflow: ``POST /evidence`` renders the packet as markdown and posts it as a comment on a
configured GitHub issue — the change ticket the team already has gains the full impact analysis
(risk factors with citations, evidence, the plan or safer alternative, the run-page link). Swap
the ``_post_comment`` call for any ITSM API to adapt it.

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

_API = "https://api.github.com"

_EVENT_TITLES = {
    "approval_requested": "Approval requested",
    "decided": "Decision recorded",
    "acknowledged": "Outcome acknowledged",
}


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


def _section(lines: list[str], title: str, rows: list[str]) -> None:
    if rows:
        lines.append(f"**{title}**")
        lines.extend(rows)
        lines.append("")


def render_markdown(packet: dict[str, object]) -> str:
    """The evidence packet as one ticket comment: decision context first, then the analysis."""
    event = str(packet.get("event", "event"))
    lines = [f"### Change Court — {_EVENT_TITLES.get(event, event)}", ""]

    change = packet.get("change")
    if isinstance(change, dict):
        lines.append(f"> {change.get('raw_request', '')}")
        lines.append("")

    risk = packet.get("risk")
    if isinstance(risk, dict):
        gate = (
            "approval required"
            if risk.get("requires_approval")
            else "no approver required — the requester's confirmation executes it"
        )
        lines.append(f"**Risk:** {str(risk.get('level', '')).upper()} ({gate})")
        factors = risk.get("factors")
        rows = []
        if isinstance(factors, list):
            for factor in factors:
                if isinstance(factor, dict):
                    citations = ", ".join(str(c) for c in factor.get("citations", []) or [])
                    suffix = f" — {citations}" if citations else ""
                    rows.append(f"- {factor.get('label')} (+{factor.get('weight')}){suffix}")
        lines.append("")
        _section(lines, "Risk factors", rows)

    impact = packet.get("impact")
    if isinstance(impact, dict):
        rows = []
        items = impact.get("items")
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    rows.append(
                        f"- [{item.get('system')}] {item.get('summary')}"
                        f" ({item.get('severity')})"
                    )
        _section(lines, "Impact evidence", rows)

    plan = packet.get("plan")
    if isinstance(plan, dict):
        kind = "Safer alternative" if plan.get("kind") == "safe_alternative" else "Proposed plan"
        rows = []
        steps = plan.get("steps")
        if isinstance(steps, list):
            rows = [
                f"- {step.get('system')}.{step.get('capability')}"
                for step in steps
                if isinstance(step, dict)
            ]
        lines.append(f"**{kind}:** {plan.get('rationale', '')}")
        lines.append("")
        _section(lines, "Steps", rows)

    quorum = packet.get("quorum")
    if isinstance(quorum, dict):
        roles = ", ".join(str(r) for r in quorum.get("required_roles", []) or [])
        if roles:
            lines.append(f"**Approvers required ({quorum.get('policy')}):** {roles}")
            lines.append("")

    if event == "decided":
        verdict = "approved" if packet.get("approved") else "rejected"
        lines.append(f"**Decision:** {verdict} by {packet.get('decider')} — {packet.get('note')}")
        lines.append("")

    run_url = packet.get("run_url")
    if run_url:
        lines.append(f"[View the full pipeline run]({run_url})")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


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
