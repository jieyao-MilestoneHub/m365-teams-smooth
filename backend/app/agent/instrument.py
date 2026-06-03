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


def _noop_duration_hook(name: str, seconds: float) -> None:
    """Default no-op sink; replaced by the in-process metrics registry in #193."""
    return None


_node_duration_hook: NodeDurationHook = _noop_duration_hook


def set_node_duration_hook(hook: NodeDurationHook) -> None:
    """Route node-duration timing to a metrics sink (wired in #193); replaces the no-op default."""
    global _node_duration_hook
    _node_duration_hook = hook


def instrument(node: Node, name: str) -> Node:
    """Wrap a court node so each call binds correlation IDs and logs start/end with a duration."""

    def wrapped(state: CourtState) -> CourtState:
        tokens = bind(thread_id=state.get("thread_id"), change_id=state.get("change_id"))
        logger.info("node.start", extra={"node": name})
        start = time.perf_counter()
        try:
            return node(state)
        finally:
            duration = time.perf_counter() - start
            logger.info("node.end", extra={"node": name, "duration_seconds": duration})
            _node_duration_hook(name, duration)
            reset(tokens)

    return wrapped
