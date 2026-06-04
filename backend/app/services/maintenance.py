"""Retention maintenance: reclaim checkpoint storage for finished trials.

The audit log is the permanent system of record and is never touched. What this purges is the
*working* storage a finished trial no longer needs: its LangGraph checkpoints (full serialized
state per node transition) and its verdict-claim rows (meaningless once the checkpoints — the only
thing a claim protects from re-execution — are gone). A trial counts as finished when it has an
audit record, which every terminal outcome (done / rejected / withdrawn) writes.

Run via ``uv run python -m scripts.purge`` (see docs/deploy.md for scheduling).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.observability import metrics
from app.ports.checkpoint import CheckpointStore
from app.ports.repository import ApprovalLedger, AuditRepository, VerdictLedger

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PurgeReport:
    """The outcome of one retention pass."""

    cutoff: str
    threads_purged: int


class MaintenanceService:
    """Purges working storage for trials that finished before the retention window."""

    def __init__(
        self,
        checkpoints: CheckpointStore,
        audit_repo: AuditRepository,
        verdicts: VerdictLedger,
        *,
        approvals: ApprovalLedger | None = None,
    ) -> None:
        self._checkpoints = checkpoints
        self._audit = audit_repo
        self._verdicts = verdicts
        self._approvals = approvals

    def purge_finished_trials(self, retention_days: int) -> PurgeReport:
        """Delete checkpoints + verdict claims for trials finished more than ``retention_days`` ago.

        Idempotent and bounded: only threads that still hold checkpoints are candidates, so the
        work shrinks to zero once a backlog is cleared. Audit records are never deleted.
        """
        cutoff = (datetime.now(UTC) - timedelta(days=retention_days)).isoformat()
        live = set(self._checkpoints.thread_ids())
        finished = set(self._audit.thread_ids_completed_before(cutoff))
        purgeable = sorted(live & finished)
        for thread_id in purgeable:
            self._checkpoints.delete_thread(thread_id)
            self._verdicts.purge_thread(thread_id)
            if self._approvals is not None:
                self._approvals.clear_pending(thread_id)  # no orphaned queue rows
        if purgeable:
            metrics.increment("maintenance.threads_purged", len(purgeable))
        logger.info(
            "maintenance.purged",
            extra={"cutoff": cutoff, "threads_purged": len(purgeable)},
        )
        return PurgeReport(cutoff=cutoff, threads_purged=len(purgeable))
