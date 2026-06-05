"""The notifier port: outbound approval notifications.

This is the approval-channel seam. The court pushes "your review is needed" / "your change was
decided" signals through this interface; concrete channels (Teams activity feed today, email or
webhooks later) plug in behind it without touching the graph, services' logic, REST, or MCP.
Notification delivery is best-effort — implementations must raise on failure and let the caller
decide; the service treats failures as non-fatal.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class ApprovalNotifier(ABC):
    """Pushes approval-workflow events to the people who must act on them."""

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
