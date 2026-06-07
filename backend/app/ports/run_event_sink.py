"""Ports for the append-only pipeline run-event log.

The sink is written from inside the running graph (node wrapper and execute node), so it must be
durable at emission time — a poller reads events while the run is still in flight — and it must be
best-effort: a failed event write never fails a real change. The reader serves the run view.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain.run_events import RunEvent, RunEventKind


class RunEventSink(ABC):
    """Append-only writer of run events. Implementations assign ``seq`` and ``created_at``."""

    @abstractmethod
    def emit(
        self,
        thread_id: str,
        kind: RunEventKind,
        name: str,
        *,
        status: str = "",
        payload: dict[str, object] | None = None,
    ) -> None:
        """Durably append one event. Best-effort: implementations swallow and log failures."""


class RunEventReader(ABC):
    """Read-side of the run-event log, for the run view."""

    @abstractmethod
    def list_after(self, thread_id: str, after_seq: int = 0) -> list[RunEvent]:
        """Events for a thread with ``seq > after_seq``, in ``seq`` order."""
