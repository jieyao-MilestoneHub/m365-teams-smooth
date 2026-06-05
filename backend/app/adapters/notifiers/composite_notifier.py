"""Composite notifier: one ``notifier`` slot, several channels (toast + bot-chat card).

Each target is guarded individually so one channel's failure never suppresses the others — the
activity-feed toast must still land when the bot chat is unreachable, and vice versa. A failure is
logged and counted; the service's own best-effort guard stays the outer net.
"""

from __future__ import annotations

import logging

from app.ports.notifier import ApprovalNotifier

logger = logging.getLogger(__name__)


class CompositeNotifier(ApprovalNotifier):
    """Fans approval events out to every configured channel."""

    def __init__(self, notifiers: list[ApprovalNotifier]) -> None:
        self._notifiers = notifiers

    def approval_requested(
        self,
        *,
        thread_id: str,
        title: str,
        requester_upn: str,
        approver_upns: list[str],
        note: str,
    ) -> None:
        for notifier in self._notifiers:
            try:
                notifier.approval_requested(
                    thread_id=thread_id,
                    title=title,
                    requester_upn=requester_upn,
                    approver_upns=approver_upns,
                    note=note,
                )
            except Exception:
                logger.warning(
                    "notify.channel_failed",
                    extra={"thread_id": thread_id, "channel": type(notifier).__name__},
                )

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
        for notifier in self._notifiers:
            try:
                notifier.decided(
                    thread_id=thread_id,
                    title=title,
                    requester_upn=requester_upn,
                    approved=approved,
                    decider_upn=decider_upn,
                    note=note,
                )
            except Exception:
                logger.warning(
                    "notify.channel_failed",
                    extra={"thread_id": thread_id, "channel": type(notifier).__name__},
                )
