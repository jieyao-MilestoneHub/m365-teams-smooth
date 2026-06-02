"""Persistence ports for the append-only audit log and the verdict idempotency ledger.

In-flight trial state (while a change awaits its verdict) lives in the graph checkpoint, not here;
these ports cover only what must outlive the graph: the audit record and the verdict ledger.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain import AuditRecord


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
