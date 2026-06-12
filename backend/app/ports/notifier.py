"""The notifier port: outbound trial-lifecycle notifications.

This is the notification-channel seam. The court pushes trial-lifecycle signals — "your review is
needed", "your change was decided", "an analysis concluded" — through this interface; concrete
channels (Teams activity feed today, email or webhooks later) plug in behind it without touching
the graph, services' logic, REST, or MCP. Notification delivery is best-effort — implementations
must raise on failure and let the caller decide; the service treats failures as non-fatal.

The abstract methods are the people-facing approval events every channel must handle. Events with
no one to act (an analysis-only conclusion) default to a no-op, so people channels stay silent
unless they opt in.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class ApprovalNotifier(ABC):
    """Pushes trial-lifecycle events to the people or systems that consume them."""

    @abstractmethod
    def approval_requested(
        self,
        *,
        thread_id: str,
        title: str,
        requester_upn: str,
        approver_upns: list[str],
        note: str,
    ) -> None:
        """Notify every approver that a trial awaits their decision."""

    @abstractmethod
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
        """Notify the requester that their trial was approved or rejected."""

    @abstractmethod
    def acknowledged(
        self,
        *,
        thread_id: str,
        title: str,
        requester_upn: str,
        approver_upns: list[str],
    ) -> None:
        """Notify the deciders that the requester confirmed the concluded outcome."""

    def analyzed(self, *, thread_id: str, title: str, requester_upn: str) -> None:
        """A trial concluded analysis-only: evidence recorded, nothing executed.

        Default no-op — there is no one who must act, so people channels stay silent. System
        channels (the evidence webhook) override this to deliver the packet to the workflow
        that asked for the analysis.
        """
        return
