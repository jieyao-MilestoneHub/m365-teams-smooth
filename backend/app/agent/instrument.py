"""Graph-node instrumentation: bind correlation IDs, log start/end + duration, emit a metric hook.

A single compile-time wrapper keeps every node uniformly observable without editing the nodes
themselves — they stay state-in/state-out and the wrapper is transparent. Applied to each node in
``graph.py:build_court_graph``.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

from app.agent.state import CourtState
from app.observability.context import bind, reset

logger = logging.getLogger(__name__)

Node = Callable[[CourtState], CourtState]
NodeDurationHook = Callable[[str, float], None]

# (thread_id, phase, node_name, payload) where phase is "started" or "finished". The emitter is a
# thin adapter over the durable RunEventSink port, installed at the composition root — the wrapper
# stays ignorant of persistence, mirroring the duration hook below.
RunEventEmitter = Callable[[str, str, str, dict[str, object]], None]


def _noop_duration_hook(name: str, seconds: float) -> None:
    """Default no-op sink; replaced by the in-process metrics registry when one is wired in."""
    return None


def _noop_run_emitter(thread_id: str, phase: str, name: str, payload: dict[str, object]) -> None:
    """Default no-op emitter; replaced by the durable run-event sink at composition."""
    return None


_node_duration_hook: NodeDurationHook = _noop_duration_hook
_run_emitter: RunEventEmitter = _noop_run_emitter


def set_node_duration_hook(hook: NodeDurationHook) -> None:
    """Route node-duration timing to a metrics sink; replaces the no-op default."""
    global _node_duration_hook
    _node_duration_hook = hook


def set_run_event_emitter(emitter: RunEventEmitter) -> None:
    """Route node started/finished events to the durable run log; replaces the no-op default."""
    global _run_emitter
    _run_emitter = emitter


def instrument(node: Node, name: str) -> Node:
    """Wrap a court node so each call binds correlation IDs and logs start/end with a duration."""

    def wrapped(state: CourtState) -> CourtState:
        thread_id = str(state.get("thread_id") or "")
        tokens = bind(thread_id=state.get("thread_id"), change_id=state.get("change_id"))
        logger.info("node.start", extra={"node": name})
        _run_emitter(thread_id, "started", name, {})
        start = time.perf_counter()
        status = ""
        try:
            result = node(state)
            if isinstance(result, dict):
                status = str(result.get("status") or "")
            return result
        finally:
            duration = time.perf_counter() - start
            logger.info("node.end", extra={"node": name, "duration_seconds": duration})
            _node_duration_hook(name, duration)
            _run_emitter(
                thread_id, "finished", name, {"duration_seconds": duration, "status": status}
            )
            reset(tokens)

    return wrapped
