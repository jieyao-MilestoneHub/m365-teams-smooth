"""Real Teams adapter: downstream writes emit a genuine Microsoft Graph activity-feed notification.

A real channel post/read (``POST``/``GET /teams/{id}/channels/{id}/messages``) is a *protected*
Graph API and intentionally out of scope. Instead, ``teams.post_message`` /
``teams.update_announcement`` send a real ``sendActivityNotification`` (app-only
``TeamsActivity.Send``) to a configured recipient — a visible, real Teams artifact — reusing the
notifier's send helper rather than duplicating the Graph call. Reads and the capability surface are
delegated to the seeded read source (the mock), so the impact node's evidence is unchanged without a
protected channel-read API. Selected when ``teams`` runs in ``real`` mode with Graph credentials and
a notify recipient configured.
"""

from __future__ import annotations

from app.adapters.integrations.base import BaseIntegrationAdapter
from app.adapters.integrations.graph import GraphClient
from app.adapters.integrations.mock_teams import MockTeamsAdapter
from app.adapters.integrations.retry import RetryClass, RetryPolicy
from app.adapters.notifiers.teams_activity import send_activity_notification
from app.domain import (
    Capability,
    ExecutionStep,
    PredictedEffect,
    RollbackHint,
)
from app.domain.errors import IntegrationError
from app.ports.integration import IntegrationAdapter, ReadQuery, ReadResult

_SYSTEM = "teams"
_WRITES = ("teams.update_announcement", "teams.post_message", "teams.create_escalation_thread")
# How each write is announced in the activity-feed toast.
_VERBS = {
    "teams.update_announcement": "Announcement",
    "teams.post_message": "Posted",
    "teams.create_escalation_thread": "Escalation",
}


class RealTeamsAdapter(BaseIntegrationAdapter):
    """Sends real Teams activity notifications on writes; delegates reads to the seeded source."""

    def __init__(
        self,
        graph: GraphClient,
        *,
        recipient_upn: str,
        link_url: str,
        teams_app_id: str = "",
        retry: RetryPolicy | None = None,
        reads: IntegrationAdapter | None = None,
    ) -> None:
        super().__init__(retry=retry)
        self._graph = graph
        self._recipient = recipient_upn
        self._link_url = link_url
        self._teams_app_id = teams_app_id
        # The seeded read source + capability catalog — reused so real and mock never diverge.
        self._reads = reads or MockTeamsAdapter()

    @property
    def system(self) -> str:
        return _SYSTEM

    def _capabilities(self) -> list[Capability]:
        # Identical surface to the mock (single source of truth), so plans and the intake guard
        # behave the same whether teams runs real or mock.
        return self._reads.capabilities()

    def _read(self, query: ReadQuery) -> ReadResult:
        # Channel reads are a protected Graph API; serve evidence from the seeded source instead.
        return self._reads.read(query)

    def _notification_text(self, step: ExecutionStep) -> str:
        channel = str(step.params.get("channel", ""))
        message = str(step.params.get("message") or step.params.get("title", ""))
        verb = _VERBS.get(step.capability.name, "Update")
        return f"{verb} — #{channel}: {message}" if channel else f"{verb} — {message}"

    def _predict(self, step: ExecutionStep, before: dict[str, object]) -> PredictedEffect:
        return PredictedEffect(
            summary=f"would send a Teams activity notification to {self._recipient}",
            diff={"recipient": self._recipient, "text": self._notification_text(step)},
        )

    def _apply(self, step: ExecutionStep) -> dict[str, object]:
        name = step.capability.name
        if name not in _WRITES:
            raise IntegrationError(f"{_SYSTEM}: unknown write capability '{name}'")
        text = self._notification_text(step)
        send_activity_notification(
            self._graph,
            recipient_upn=self._recipient,
            text=text,
            chain_seed=step.step_id,
            link_url=self._link_url,
            teams_app_id=self._teams_app_id,
        )
        return {"notified": self._recipient, "text": text, "capability": name}

    def _fetch_before(self, step: ExecutionStep) -> dict[str, object]:
        return {}  # a feed notification has no prior state to capture

    def _retry_class_for(self, step: ExecutionStep) -> RetryClass:
        # An activity notification is NOT idempotent — a retry sends a duplicate toast. Override the
        # base's ".update_ => LIBERAL" rule so teams.update_announcement only retries when the
        # request provably never landed.
        return RetryClass.NEVER_LANDED

    def _rollback(self, step: ExecutionStep, before: dict[str, object]) -> RollbackHint:
        return RollbackHint(
            step_id=step.step_id,
            system=_SYSTEM,
            instruction=(
                "an activity-feed notification cannot be recalled; send a correcting notification "
                "if needed"
            ),
            params=dict(step.params),
        )
