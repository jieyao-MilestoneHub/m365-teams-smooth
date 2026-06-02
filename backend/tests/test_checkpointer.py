"""The SQLite checkpoint store backs a real LangGraph run: state persists by thread_id."""

from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.adapters.persistence.checkpointer import SqliteCheckpointStore


class _S(TypedDict, total=False):
    n: int


def _increment(state: _S) -> _S:
    return {"n": state.get("n", 0) + 1}


def test_state_persists_under_thread_id() -> None:
    store = SqliteCheckpointStore(":memory:")
    store.setup()

    graph = StateGraph(_S)
    graph.add_node("inc", _increment)
    graph.add_edge(START, "inc")
    graph.add_edge("inc", END)
    app = graph.compile(checkpointer=store.saver())  # type: ignore[arg-type]

    config = {"configurable": {"thread_id": "t1"}}
    app.invoke({"n": 0}, config)  # type: ignore[call-overload]

    # A read of the same thread sees the checkpointed value.
    assert app.get_state(config).values["n"] == 1  # type: ignore[arg-type]


def test_from_db_url_uses_memory_for_non_sqlite() -> None:
    store = SqliteCheckpointStore.from_db_url("postgresql://x")
    store.setup()
    assert store.saver() is not None
