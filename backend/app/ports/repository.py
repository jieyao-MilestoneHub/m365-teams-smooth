"""Persistence ports for the append-only audit log and the verdict idempotency ledger.

In-flight trial state (while a change awaits its verdict) lives in the graph checkpoint, not here;
these ports cover only what must outlive the graph: the audit record and the verdict ledger.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain import ApprovalDecision, ApprovalEvent, AuditRecord


class AuditRepository(ABC):
    """Append-only store of trial audit records. Records are never updated."""

    @abstractmethod
    def append(self, record: AuditRecord) -> None:
        """Persist a new audit record."""

    @abstractmethod
    def get(self, audit_id: str) -> AuditRecord | None:
        """Fetch a record by id, or ``None``."""

    @abstractmethod
    def latest_for_change(self, change_id: str) -> AuditRecord | None:
        """Fetch the most recent record for a change, or ``None``."""


class VerdictLedger(ABC):
    """Idempotency ledger making a cast verdict exactly-once across REST and MCP.

    The service claims a verdict before resuming the graph; a second claim with the same key is
    rejected and the caller returns the already-recorded result instead of re-executing.
    """

    @abstractmethod
    def try_claim(self, thread_id: str, idempotency_key: str) -> bool:
        """Atomically claim the key. ``True`` if newly claimed, ``False`` if already seen."""

    @abstractmethod
    def mark_completed(self, thread_id: str, idempotency_key: str, audit_id: str) -> None:
        """Record the audit id produced by a claimed verdict's execution."""

    @abstractmethod
    def result_for(self, thread_id: str, idempotency_key: str) -> str | None:
        """Return the audit id recorded for a completed verdict, or ``None``."""


class ApprovalLedger(ABC):
    """Append-only log of approval actions (send/withdraw/approve/reject) per trial.

    The service folds these events (via :func:`app.domain.evaluate_quorum`) to decide whether a
    trial may resume into execution. Records are never updated.
    """

    @abstractmethod
    def append(self, event: ApprovalEvent) -> None:
        """Persist a new approval event."""

    @abstractmethod
    def list_for_thread(self, thread_id: str) -> list[ApprovalEvent]:
        """Return all approval events for a trial, in insertion order."""

    @abstractmethod
    def thread_ids(self) -> list[str]:
        """Return the distinct thread ids that have at least one approval event (for the queue)."""

    @abstractmethod
    def first_note(self, thread_id: str, decision: ApprovalDecision) -> str:
        """The note on the earliest event of ``decision`` for a trial, or empty."""

    @abstractmethod
    def mark_pending(self, thread_id: str, at: str) -> None:
        """Add a trial to the pending-approvals index (idempotent)."""

    @abstractmethod
    def clear_pending(self, thread_id: str) -> None:
        """Remove a trial from the pending-approvals index (no-op when absent)."""

    @abstractmethod
    def pending_thread_ids(self) -> list[str]:
        """Trials currently awaiting an approver — the queue reads this, never the full history."""
