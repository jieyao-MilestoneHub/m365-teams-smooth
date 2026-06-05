"""Teams activity-feed notifier: pushes approval events as native Teams notifications.

Uses Microsoft Graph ``sendActivityNotification`` (app-only, ``TeamsActivity.Send``): the recipient
gets a toast + activity-feed entry that deep-links back into Teams, so approvers act on a push
instead of polling the queue. Failures raise; the service treats notification delivery as
best-effort.

Graph contract, verified live against the deployed tenant:
- ``topic.webUrl`` must be a Teams deep link ("…/l/…"); a bare domain is rejected (400).
- Custom activity types declared in the manifest were accepted (204) but silently dropped by the
  feed, while the reserved ``systemDefault`` type — free-form text via the ``systemDefaultText``
  template parameter — delivers reliably, so that is what this adapter sends.
- ``teamsAppId`` (the *catalog* app id, not the manifest id) disambiguates the installed app.

Each trial's notifications share a ``chainId`` derived from the thread id, so a newer event for the
same trial overrides the previous toast in the recipient's feed instead of stacking next to it.
"""

from __future__ import annotations

from hashlib import sha256

import httpx

from app.adapters.integrations.graph import GraphClient
from app.ports.notifier import ApprovalNotifier

_TOPIC_VALUE = "AI Change Court"


def _chain_id(thread_id: str) -> int:
    """A stable positive Int64 for the trial, as Graph expects for notification chaining."""
    digest = sha256(thread_id.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") & 0x7FFF_FFFF_FFFF_FFFF


class TeamsActivityNotifier(ApprovalNotifier):
    """Delivers approval notifications to users' Teams activity feeds via Graph."""

    def __init__(self, graph: GraphClient, *, link_url: str, teams_app_id: str = "") -> None:
        self._graph = graph
        self._link_url = link_url
        self._teams_app_id = teams_app_id

    def _send(self, upn: str, text: str, thread_id: str) -> None:
        payload: dict[str, object] = {
            "topic": {"source": "text", "value": _TOPIC_VALUE, "webUrl": self._link_url},
            "activityType": "systemDefault",
            "previewText": {"content": text[:150]},
            "templateParameters": [{"name": "systemDefaultText", "value": text[:150]}],
            "chainId": _chain_id(thread_id),
        }
        if self._teams_app_id:
            payload["teamsAppId"] = self._teams_app_id
        try:
            self._graph.post(f"/users/{upn}/teamwork/sendActivityNotification", payload)
        except httpx.HTTPStatusError as err:
            # Surface Graph's error body — the status line alone ("400 Bad Request") hides the
            # actionable reason (e.g. an activity-type/template mismatch with the installed app).
            raise RuntimeError(f"{err} — {err.response.text[:300]}") from err

    def approval_requested(
        self,
        *,
        thread_id: str,
        title: str,
        requester_upn: str,
        approver_upns: list[str],
        note: str,
    ) -> None:
        # Lead with the requester's note — it is their (required) justification and the most useful
        # content. The 150-char activity-feed cap would truncate it off the end if it trailed the
        # title; the full title/impact live on the bot card the toast links to.
        summary = note or title
        text = f"Approval needed — {requester_upn}: {summary}"
        for upn in approver_upns:
            self._send(upn, text, thread_id)

    def decided(
        self,
        *,
        thread_id: str,
        title: str,
        requester_upn: str,
        approved: bool,
        decider_upn: str,
        note: str,
    ) -> None:
        if not requester_upn:
            return
        outcome = "approved" if approved else "rejected"
        # Lead with the note (it carries the decider's reason and the execution outcome summary),
        # which would otherwise be truncated off the end behind the title.
        summary = note or title
        text = f"{decider_upn} {outcome}: {summary}"
        self._send(requester_upn, text, thread_id)

    def acknowledged(
        self,
        *,
        thread_id: str,
        title: str,
        requester_upn: str,
        approver_upns: list[str],
    ) -> None:
        # Same chainId as the trial's earlier toasts, so the ack overrides rather than stacks.
        text = f"{requester_upn} acknowledged the outcome: {title}"
        for upn in approver_upns:
            self._send(upn, text, thread_id)
