"""Run-event log: durable append with monotonic per-thread seq and incremental reads."""

from __future__ import annotations

from app.adapters.persistence.db import init_db, make_engine, make_session_factory
from app.adapters.persistence.repositories import SqlRunEventSink
from app.domain.run_events import RunEventKind


def _sink() -> SqlRunEventSink:
    engine = make_engine("sqlite:///:memory:")
    init_db(engine)
    return SqlRunEventSink(make_session_factory(engine))


def test_emit_assigns_monotonic_seq_per_thread() -> None:
    sink = _sink()
    sink.emit("t1", RunEventKind.NODE_STARTED, "intake")
    sink.emit("t1", RunEventKind.NODE_FINISHED, "intake", status="evaluating")
    sink.emit("t2", RunEventKind.NODE_STARTED, "intake")

    assert [e.seq for e in sink.list_after("t1")] == [1, 2]
    assert [e.seq for e in sink.list_after("t2")] == [1]  # threads number independently


def test_list_after_filters_and_orders() -> None:
    sink = _sink()
    for name in ("intake", "impact", "options"):
        sink.emit("t1", RunEventKind.NODE_STARTED, name)

    tail = sink.list_after("t1", after_seq=1)
    assert [(e.seq, e.name) for e in tail] == [(2, "impact"), (3, "options")]
    assert sink.list_after("t1", after_seq=3) == []


def test_finished_event_carries_status_payload_and_timestamp() -> None:
    sink = _sink()
    sink.emit(
        "t1",
        RunEventKind.STEP_FINISHED,
        "s1",
        status="dry_run",
        payload={"system": "github", "capability": "github.update_milestone_due"},
    )

    event = sink.list_after("t1")[0]
    assert event.kind is RunEventKind.STEP_FINISHED
    assert event.status == "dry_run"
    assert event.payload["system"] == "github"
    assert event.created_at  # stamped at the sink edge


def test_empty_thread_id_is_dropped() -> None:
    # Nodes exercised outside a trial (unit tests, ad-hoc runs) have no run log to write to.
    sink = _sink()
    sink.emit("", RunEventKind.NODE_STARTED, "intake")
    assert sink.list_after("") == []


def test_emit_swallows_persistence_failures() -> None:
    # Observability must never fail a change: a broken session factory is logged, not raised.
    def broken() -> None:
        raise RuntimeError("db down")

    sink = SqlRunEventSink(broken)  # type: ignore[arg-type]
    sink.emit("t1", RunEventKind.NODE_STARTED, "intake")  # must not raise
