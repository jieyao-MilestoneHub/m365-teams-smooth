"""In-memory notifier: records every notification for assertions and identity-free local runs."""

from __future__ import annotations

from app.ports.notifier import ApprovalNotifier


class FakeNotifier(ApprovalNotifier):
    """Collects notifications instead of delivering them."""

    def __init__(self) -> None:
        self.requested: list[dict[str, object]] = []
        self.decisions: list[dict[str, object]] = []

    def approval_requested(
        self,
        *,
        thread_id: str,
        title: str,
        requester_upn: str,
        approver_upns: list[str],
        note: str,
    ) -> None:
        self.requested.append(
            {
                "thread_id": thread_id,
                "title": title,
                "requester_upn": requester_upn,
                "approver_upns": approver_upns,
                "note": note,
            }
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
        self.decisions.append(
            {
                "thread_id": thread_id,
                "title": title,
                "requester_upn": requester_upn,
                "approved": approved,
                "decider_upn": decider_upn,
                "note": note,
            }
        )
