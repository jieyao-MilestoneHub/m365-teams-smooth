"""In-process metrics: a tiny thread-safe counter/timer registry, exposed as ``court://metrics``.

No exposition format or external collector (see ADR-0005) — a single-process registry that an
OTLP/Prometheus exporter could later attach to. Collection is gated by ``metrics_enabled``; when
disabled, increments are no-ops and the snapshot reports ``enabled: false`` with empty series.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.config import Settings


@dataclass
class _Timer:
    count: int = 0
    total_seconds: float = 0.0


class MetricsRegistry:
    """Lock-guarded counters and timers; safe to increment from concurrent threads."""

    def __init__(self, *, enabled: bool = True) -> None:
        self._enabled = enabled
        self._lock = threading.Lock()
        self._counters: dict[str, int] = {}
        self._timers: dict[str, _Timer] = {}

    def increment(self, name: str, amount: int = 1) -> None:
        if not self._enabled:
            return
        with self._lock:
            self._counters[name] = self._counters.get(name, 0) + amount

    def observe(self, name: str, seconds: float) -> None:
        if not self._enabled:
            return
        with self._lock:
            timer = self._timers.setdefault(name, _Timer())
            timer.count += 1
            timer.total_seconds += seconds

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return {
                "enabled": self._enabled,
                "counters": dict(self._counters),
                "timers": {
                    name: {"count": t.count, "total_seconds": t.total_seconds}
                    for name, t in self._timers.items()
                },
            }


_registry = MetricsRegistry()


def increment(name: str, amount: int = 1) -> None:
    """Add to a process-wide counter (no-op when metrics are disabled)."""
    _registry.increment(name, amount)


def observe(name: str, seconds: float) -> None:
    """Record a duration sample against a process-wide timer (no-op when disabled)."""
    _registry.observe(name, seconds)


def snapshot() -> dict[str, object]:
    """The current counters and timers, plus the ``enabled`` flag."""
    return _registry.snapshot()


def _record_node_duration(name: str, seconds: float) -> None:
    observe(f"node.{name}.duration", seconds)


def configure_metrics(settings: Settings) -> None:
    """(Re)build the registry per ``metrics_enabled`` and light up the node-duration hook."""
    global _registry
    _registry = MetricsRegistry(enabled=settings.metrics_enabled)
    # Point the no-op node-duration hook at the live registry.
    from app.agent.instrument import set_node_duration_hook

    set_node_duration_hook(_record_node_duration)
