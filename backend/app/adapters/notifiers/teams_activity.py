"""Teams activity-feed notifier: pushes approval events as native Teams notifications.

Uses Microsoft Graph ``sendActivityNotification`` (app-only, ``TeamsActivity.Send``): the recipient
gets a toast + activity-feed entry that deep-links back into Teams, so approvers act on a push
instead of polling the queue. Activity types here must be declared in the Teams app manifest's
``activities`` section. Failures raise; the service treats notification delivery as best-effort.
"""

from __future__ import annotations

from app.adapters.integrations.graph import GraphClient
from app.ports.notifier import ApprovalNotifier

_TOPIC_VALUE = "AI Change Court"


class TeamsActivityNotifier(ApprovalNotifier):
    """Delivers approval notifications to users' Teams activity feeds via Graph."""

    def __init__(self, graph: GraphClient, *, link_url: str) -> None:
        self._graph = graph
        self._link_url = link_url

    def _send(self, upn: str, activity_type: str, preview: str) -> None:
        # Graph contract, learned live: topic.webUrl must be a Teams deep link ("…/l/…"), and
        # the manifest template's ``{actor}`` is reserved — Graph fills it with the caller and
        # rejects it as an explicit template parameter (400).
        self._graph.post(
            f"/users/{upn}/teamwork/sendActivityNotification",
            {
                "topic": {"source": "text", "value": _TOPIC_VALUE, "webUrl": self._link_url},
                "activityType": activity_type,
                "previewText": {"content": preview[:150]},
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
        preview = f"{requester_upn}: {title}" + (f" — {note}" if note else "")
        for upn in approver_upns:
            self._send(upn, "approvalRequired", preview)

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
        preview = f"{decider_upn} {outcome}: {title}" + (f" — {note}" if note else "")
        self._send(requester_upn, "trialDecided", preview)
