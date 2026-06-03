"""In-process metrics registry, the node-duration hook wiring, and the court://metrics resource."""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from typing import Any

import pytest

from app.agent import instrument as instrument_module
from app.agent.instrument import _noop_duration_hook, instrument, set_node_duration_hook
from app.agent.state import CourtState
from app.config import Settings
from app.container import build_court_service
from app.mcp.server import build_mcp_server
from app.observability import metrics
from app.observability.metrics import MetricsRegistry, configure_metrics
from app.services.court_service import CourtService


@pytest.fixture
def restore_hook() -> Iterator[None]:
    """Tests that call configure_metrics mutate the global node-duration hook; restore the no-op."""
    try:
        yield
    finally:
        set_node_duration_hook(_noop_duration_hook)


def test_counter_increment_and_snapshot() -> None:
    registry = MetricsRegistry()
    registry.increment("trials.submitted")
    registry.increment("trials.submitted", 2)

    snap = registry.snapshot()
    assert snap["enabled"] is True
    assert snap["counters"] == {"trials.submitted": 3}


def test_timer_observe_and_snapshot() -> None:
    registry = MetricsRegistry()
    registry.observe("node.intake.duration", 0.5)
    registry.observe("node.intake.duration", 1.5)

    timers = registry.snapshot()["timers"]
    assert timers == {"node.intake.duration": {"count": 2, "total_seconds": 2.0}}


def test_disabled_registry_is_noop() -> None:
    registry = MetricsRegistry(enabled=False)
    registry.increment("trials.submitted")
    registry.observe("node.intake.duration", 1.0)

    snap = registry.snapshot()
    assert snap["enabled"] is False
    assert snap["counters"] == {}
    assert snap["timers"] == {}


def test_registry_is_thread_safe() -> None:
    registry = MetricsRegistry()
    threads = 10
    per_thread = 1000

    def worker() -> None:
        for _ in range(per_thread):
            registry.increment("hits")

    workers = [threading.Thread(target=worker) for _ in range(threads)]
    for t in workers:
        t.start()
    for t in workers:
        t.join()

    assert registry.snapshot()["counters"] == {"hits": threads * per_thread}


def test_configure_metrics_wires_node_duration_hook(restore_hook: None) -> None:
    configure_metrics(Settings(_env_file=None, metrics_enabled=True))  # type: ignore[call-arg]
    assert instrument_module._node_duration_hook is metrics._record_node_duration

    instrument(lambda state: state, "intake")(CourtState(thread_id="t1", change_id="c1"))

    timers = metrics.snapshot()["timers"]
    assert isinstance(timers, dict)
    assert "node.intake.duration" in timers


def test_configure_metrics_disabled_collects_nothing(restore_hook: None) -> None:
    configure_metrics(Settings(_env_file=None, metrics_enabled=False))  # type: ignore[call-arg]
    metrics.increment("trials.submitted")

    snap = metrics.snapshot()
    assert snap["enabled"] is False
    assert snap["counters"] == {}


@pytest.fixture
def service() -> CourtService:
    return build_court_service(
        Settings(force_all_mock=True, db_url="sqlite:///:memory:", dry_run_default=True)
    )


async def _read(mcp: Any, uri: str) -> Any:
    contents = await mcp.read_resource(uri)
    return json.loads(contents[0].content)


async def test_metrics_resource_returns_snapshot(
    service: CourtService, restore_hook: None
) -> None:
    configure_metrics(Settings(_env_file=None, metrics_enabled=True))  # type: ignore[call-arg]
    metrics.increment("trials.submitted")

    payload = await _read(build_mcp_server(service), "court://metrics")

    assert payload["enabled"] is True
    assert payload["counters"]["trials.submitted"] >= 1
