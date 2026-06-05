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
"""

from __future__ import annotations

from app.adapters.integrations.graph import GraphClient
from app.ports.notifier import ApprovalNotifier

_TOPIC_VALUE = "AI Change Court"


class TeamsActivityNotifier(ApprovalNotifier):
    """Delivers approval notifications to users' Teams activity feeds via Graph."""

    def __init__(self, graph: GraphClient, *, link_url: str, teams_app_id: str = "") -> None:
        self._graph = graph
        self._link_url = link_url
        self._teams_app_id = teams_app_id

    def _send(self, upn: str, text: str) -> None:
        payload: dict[str, object] = {
            "topic": {"source": "text", "value": _TOPIC_VALUE, "webUrl": self._link_url},
            "activityType": "systemDefault",
            "previewText": {"content": text[:150]},
            "templateParameters": [{"name": "systemDefaultText", "value": text[:150]}],
        }
        if self._teams_app_id:
            payload["teamsAppId"] = self._teams_app_id
        self._graph.post(f"/users/{upn}/teamwork/sendActivityNotification", payload)

    def approval_requested(
        self,
        *,
        thread_id: str,
        title: str,
        requester_upn: str,
        approver_upns: list[str],
        note: str,
    ) -> None:
        text = f"Approval needed — {requester_upn}: {title}" + (f" — {note}" if note else "")
        for upn in approver_upns:
            self._send(upn, text)

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
        text = f"{decider_upn} {outcome}: {title}" + (f" — {note}" if note else "")
        self._send(requester_upn, text)
