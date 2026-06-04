"""CourtRunner: start a run to the verdict gate, then resume it from the checkpoint.

The compiled graph is treated opaquely (typed ``Any``) so all LangGraph API specifics stay here.
The graph is never held across the verdict gap — both ``start`` and ``resume`` operate purely
through the checkpoint keyed by ``thread_id``, so a fresh runner can resume a run begun elsewhere.
``resume`` is idempotent at this layer: once a run is past the gate, a repeat resume is a no-op.
"""

from __future__ import annotations

import concurrent.futures
from typing import Any, cast

from app.agent.state import CourtState, serialize
from app.domain import Verdict
from app.domain.errors import GraphTimeoutError


class CourtRunner:
    """Drives the court graph across the durable verdict interrupt."""

    def __init__(self, graph: Any, *, timeout_seconds: float | None = None) -> None:
        self._graph = graph
        self._timeout_seconds = timeout_seconds

    @staticmethod
    def _config(thread_id: str) -> dict[str, Any]:
        return {"configurable": {"thread_id": thread_id}}

    def start(self, thread_id: str, state: CourtState) -> CourtState:
        """Run intake → … → policy; the graph suspends before execute and persists a checkpoint."""
        config = self._config(thread_id)
        self._invoke(state, config, thread_id)
        return self.state(thread_id)

    def resume(self, thread_id: str, verdict: Verdict) -> CourtState:
        """Record the verdict and resume into execute → audit. A completed run is left untouched."""
        config = self._config(thread_id)
        snapshot = self._graph.get_state(config)
        if not snapshot.next:
            # Already past the verdict gate — idempotent: do not execute again.
            return cast(CourtState, snapshot.values)
        self._graph.update_state(
            config,
            {"verdict": serialize(verdict), "selected_plan": verdict.selected_plan.value},
        )
        self._invoke(None, config, thread_id)
        return self.state(thread_id)

    def _invoke(
        self, input_state: CourtState | None, config: dict[str, Any], thread_id: str
    ) -> None:
        """Run the graph, guarded by an optional wall-clock budget.

        With no budget the graph runs inline (current behavior). With one, it runs in a worker
        thread joined with a timeout — the only cross-platform way to bound a synchronous run
        (Windows has no SIGALRM). On expiry a typed ``GraphTimeoutError`` is raised; the
        checkpointer has already persisted each completed node, so the checkpoint stays intact and
        resumable, while the abandoned worker finishes in the background.
        """
        if self._timeout_seconds is None:
            self._graph.invoke(input_state, config)
            return
        pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        future = pool.submit(self._graph.invoke, input_state, config)
        try:
            future.result(timeout=self._timeout_seconds)
        except concurrent.futures.TimeoutError as exc:
            raise GraphTimeoutError(
                f"graph run for thread '{thread_id}' exceeded {self._timeout_seconds}s"
            ) from exc
        finally:
            pool.shutdown(wait=False)

    def update(self, thread_id: str, values: dict[str, Any]) -> CourtState:
        """Persist a partial state update on the suspended checkpoint without resuming.

        Used by the requester-review gate (record the requester / their note / the new status) while
        the run waits at the verdict interrupt — the graph is not advanced.
        """
        self._graph.update_state(self._config(thread_id), values)
        return self.state(thread_id)

    def state(self, thread_id: str) -> CourtState:
        """The current checkpointed state for a thread."""
        return cast(CourtState, self._graph.get_state(self._config(thread_id)).values)

    def is_awaiting_verdict(self, thread_id: str) -> bool:
        """True when the run is suspended at the verdict gate (execute is the next node)."""
        return "execute" in (self._graph.get_state(self._config(thread_id)).next or ())
