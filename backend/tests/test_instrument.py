"""Graph-node instrumentation: binding, start/end logs, the metric hook, and graph wiring."""

from __future__ import annotations

import logging
from collections.abc import Iterator

import pytest

from app.adapters.persistence.checkpointer import SqliteCheckpointStore
from app.agent import instrument as instrument_module
from app.agent.graph import build_court_graph
from app.agent.instrument import _noop_duration_hook, instrument, set_node_duration_hook
from app.agent.state import CourtState, initial_state
from app.domain import RunMode
from app.observability.context import current_context


class _CaptureHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@pytest.fixture
def captured() -> Iterator[list[logging.LogRecord]]:
    handler = _CaptureHandler()
    logger = logging.getLogger("app.agent.instrument")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        yield handler.records
    finally:
        logger.removeHandler(handler)


def _state() -> CourtState:
    return CourtState(thread_id="t1", change_id="c1")


def test_instrument_preserves_return_value() -> None:
    def node(state: CourtState) -> CourtState:
        return CourtState(status="done")

    assert instrument(node, "audit")(_state()) == {"status": "done"}


def test_instrument_binds_ids_during_call_and_resets_after() -> None:
    seen: dict[str, str] = {}

    def node(state: CourtState) -> CourtState:
        seen.update(current_context())
        return state

    instrument(node, "intake")(_state())

    assert seen == {"thread_id": "t1", "change_id": "c1"}
    assert current_context() == {}  # no leak after the call


def test_instrument_logs_start_and_end_with_duration(captured: list[logging.LogRecord]) -> None:
    instrument(lambda state: state, "impact")(_state())

    assert [r.getMessage() for r in captured] == ["node.start", "node.end"]
    end = captured[1]
    assert end.__dict__["node"] == "impact"
    assert isinstance(end.__dict__["duration_seconds"], float)


def test_metric_hook_is_noop_safe() -> None:
    # With the default hook installed, instrumenting must not raise.
    instrument(lambda state: state, "policy")(_state())


def test_set_node_duration_hook_routes_timing() -> None:
    calls: list[tuple[str, float]] = []
    set_node_duration_hook(lambda name, seconds: calls.append((name, seconds)))
    try:
        instrument(lambda state: state, "execute")(_state())
    finally:
        set_node_duration_hook(_noop_duration_hook)

    assert calls[0][0] == "execute"
    assert isinstance(calls[0][1], float)


def test_instrument_resets_hook_isolation() -> None:
    # The module default must be the no-op after the previous test restored it.
    assert instrument_module._node_duration_hook is _noop_duration_hook


def test_build_court_graph_instruments_each_node(captured: list[logging.LogRecord]) -> None:
    store = SqliteCheckpointStore(":memory:")
    store.setup()

    def identity(state: CourtState) -> CourtState:
        return state

    graph = build_court_graph(
        intake=identity,
        impact=identity,
        options=identity,
        policy=identity,
        execute=identity,
        audit=identity,
        checkpointer=store.saver(),
    )

    state = initial_state(
        thread_id="t1", change_id="c1", raw_request="x", source="t", run_mode=RunMode.DRY_RUN
    )
    # interrupt_before=["execute"] suspends the run after policy, before execute.
    graph.invoke(state, {"configurable": {"thread_id": "t1"}})

    started = {r.__dict__["node"] for r in captured if r.getMessage() == "node.start"}
    assert {"intake", "impact", "options", "policy"} <= started
