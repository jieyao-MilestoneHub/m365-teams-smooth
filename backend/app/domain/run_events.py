"""Pipeline run events: the append-only record of a trial's node-by-node progress.

Each graph node emits a started/finished pair, and the execute node additionally emits one pair
per plan step, so a run can be replayed or observed live (the run page polls these while the
graph is still executing). Approval actions are NOT recorded here — the approval ledger
(:mod:`app.domain.approval`) is their single home and the run view folds them in at read time.

Like the other domain modules this imports no framework; ``seq`` and ``created_at`` are assigned
at the sink edge so the model stays deterministic and pure.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class RunEventKind(StrEnum):
    """What a run event marks: a node boundary or an execution-step boundary."""

    NODE_STARTED = "node_started"
    NODE_FINISHED = "node_finished"
    STEP_STARTED = "step_started"
    STEP_FINISHED = "step_finished"


class RunEvent(BaseModel):
    """One append-only progress event in a trial's pipeline run. Never mutated.

    ``name`` is the node name (``intake`` … ``audit``) for node events and the ``step_id`` for
    step events. ``status`` is empty for ``*_started``; for ``node_finished`` it carries the
    node's resulting trial status and for ``step_finished`` the step's
    :class:`~app.domain.enums.StepStatus` value. ``payload`` holds the small extras a viewer
    needs (``duration_seconds``, ``system``, ``capability``, ``run_mode``, ``error``).
    """

    thread_id: str
    seq: int  # monotonic per thread, assigned by the sink
    kind: RunEventKind
    name: str
    status: str = ""
    payload: dict[str, object] = Field(default_factory=dict)
    created_at: str = ""  # ISO-8601 UTC, stamped at the sink edge
