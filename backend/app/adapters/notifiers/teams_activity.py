"""Teams activity-feed notifier: pushes approval events as native Teams notifications.

Uses Microsoft Graph ``sendActivityNotification`` (app-only, ``TeamsActivity.Send``): the recipient
gets a toast + activity-feed entry that deep-links back into Teams, so approvers act on a push
instead of polling the queue. Activity types here must be declared in the Teams app manifest's
``activities`` section. Failures raise; the service treats notification delivery as best-effort.

Each trial's notifications share a ``chainId`` derived from the thread id, so a newer event for the
same trial overrides the previous toast in the recipient's feed instead of stacking next to it.
"""

from __future__ import annotations

from hashlib import sha256

from app.adapters.integrations.graph import GraphClient
from app.ports.notifier import ApprovalNotifier

_TOPIC_VALUE = "AI Change Court"


def _chain_id(thread_id: str) -> int:
    """A stable positive Int64 for the trial, as Graph expects for notification chaining."""
    digest = sha256(thread_id.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") & 0x7FFF_FFFF_FFFF_FFFF


class TeamsActivityNotifier(ApprovalNotifier):
    """Delivers approval notifications to users' Teams activity feeds via Graph."""

    def __init__(self, graph: GraphClient, *, link_url: str) -> None:
        self._graph = graph
        self._link_url = link_url

    def _send(
        self, upn: str, activity_type: str, preview: str, actor: str, thread_id: str
    ) -> None:
        self._graph.post(
            f"/users/{upn}/teamwork/sendActivityNotification",
            {
                "topic": {"source": "text", "value": _TOPIC_VALUE, "webUrl": self._link_url},
                "activityType": activity_type,
                "previewText": {"content": preview[:150]},
                "templateParameters": [{"name": "actor", "value": actor}],
                "chainId": _chain_id(thread_id),
            },
        )

    def approval_requested(
        self,
        *,
        thread_id: str,
        title: str,
        requester_upn: str,
        approver_upns: list[str],
        note: str,
    ) -> None:
        preview = f"{title} — {note}" if note else title
        for upn in approver_upns:
            self._send(upn, "approvalRequired", preview, requester_upn or _TOPIC_VALUE, thread_id)

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
        preview = f"{title} — {outcome}" + (f": {note}" if note else "")
        self._send(requester_upn, "trialDecided", preview, decider_upn or _TOPIC_VALUE, thread_id)
