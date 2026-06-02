"""CourtState holds JSON-safe data and round-trips domain models losslessly."""

from __future__ import annotations

from app.agent.state import initial_state, serialize
from app.domain import Change, ChangeStatus, RunMode


def test_initial_state_defaults() -> None:
    state = initial_state(
        thread_id="t1",
        change_id="c1",
        raw_request="slip the launch",
        source="test",
        run_mode=RunMode.DRY_RUN,
    )
    assert state["run_mode"] == "dry_run"
    assert state["status"] == ChangeStatus.INTAKE.value
    assert state["results"] == []


def test_serialize_round_trips_through_state() -> None:
    change = Change(change_id="c1", raw_request="slip the launch")
    state = initial_state(
        thread_id="t1",
        change_id="c1",
        raw_request="slip the launch",
        source="test",
        run_mode=RunMode.DRY_RUN,
    )
    state["change"] = serialize(change)
    # the stored value is a plain dict and rehydrates to an equal model
    assert isinstance(state["change"], dict)
    assert Change.model_validate(state["change"]) == change
