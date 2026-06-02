"""CourtRunner: start a run to the verdict gate, then resume it from the checkpoint.

The compiled graph is treated opaquely (typed ``Any``) so all LangGraph API specifics stay here.
The graph is never held across the verdict gap — both ``start`` and ``resume`` operate purely
through the checkpoint keyed by ``thread_id``, so a fresh runner can resume a run begun elsewhere.
``resume`` is idempotent at this layer: once a run is past the gate, a repeat resume is a no-op.
"""

from __future__ import annotations

from typing import Any, cast

from app.agent.state import CourtState, serialize
from app.domain import Verdict


class CourtRunner:
    """Drives the court graph across the durable verdict interrupt."""

    def __init__(self, graph: Any) -> None:
        self._graph = graph

    @staticmethod
    def _config(thread_id: str) -> dict[str, Any]:
        return {"configurable": {"thread_id": thread_id}}

    def start(self, thread_id: str, state: CourtState) -> CourtState:
        """Run intake → … → policy; the graph suspends before execute and persists a checkpoint."""
        config = self._config(thread_id)
        self._graph.invoke(state, config)
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
        self._graph.invoke(None, config)
        return self.state(thread_id)

    def state(self, thread_id: str) -> CourtState:
        """The current checkpointed state for a thread."""
        return cast(CourtState, self._graph.get_state(self._config(thread_id)).values)

    def is_awaiting_verdict(self, thread_id: str) -> bool:
        """True when the run is suspended at the verdict gate (execute is the next node)."""
        return "execute" in (self._graph.get_state(self._config(thread_id)).next or ())
