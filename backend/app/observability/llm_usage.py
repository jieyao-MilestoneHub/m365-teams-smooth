"""Per-node LLM usage accumulation, drained into the durable run-event log.

The recording provider (``adapters/llm/usage_recording.py``) records each call's token usage into a
``threading.local`` slot; the node instrumentation wrapper drains the slot into the node's
``node_finished`` run event. Summing durable events keeps per-trial totals correct across the
verdict interrupt (a trial spans multiple requests), and thread-locals keep concurrent trials on
one replica from cross-contaminating: a graph invocation runs its nodes on a single thread.

Contract: only LLM calls made synchronously on the node's own thread are attributed. A call made
from a spawned worker thread lands in that thread's slot and is dropped at reset — never
misattributed to another node or trial.
"""

from __future__ import annotations

import threading


class _Slot(threading.local):
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0

    def __init__(self) -> None:  # runs once per thread
        self.deployments: set[str] = set()


_slot = _Slot()


def record(model: str, *, input_tokens: int, output_tokens: int, cached_tokens: int) -> None:
    """Add one successful LLM call's usage to the current thread's slot."""
    _slot.calls += 1
    _slot.input_tokens += input_tokens
    _slot.output_tokens += output_tokens
    _slot.cached_tokens += cached_tokens
    if model:
        _slot.deployments.add(model)


def reset() -> None:
    """Clear the current thread's slot (called at node start to guard thread reuse)."""
    _slot.calls = 0
    _slot.input_tokens = 0
    _slot.output_tokens = 0
    _slot.cached_tokens = 0
    _slot.deployments = set()


def drain() -> dict[str, object] | None:
    """Return and clear the current thread's usage; ``None`` when no calls were recorded."""
    if _slot.calls == 0:
        reset()
        return None
    usage: dict[str, object] = {
        "calls": _slot.calls,
        "input_tokens": _slot.input_tokens,
        "output_tokens": _slot.output_tokens,
        "cached_tokens": _slot.cached_tokens,
        "deployments": sorted(_slot.deployments),
    }
    reset()
    return usage
