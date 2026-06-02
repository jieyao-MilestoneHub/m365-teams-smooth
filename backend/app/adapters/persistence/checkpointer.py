"""SQLite checkpoint store: wraps LangGraph's SqliteSaver behind the CheckpointStore port.

This is the only place the LangGraph saver type appears, so swapping SQLite for Postgres later is
a new adapter with no change to the graph or services. The store holds a raw sqlite3 connection
(shared across threads) backing the checkpoint tables that persist a run across the verdict gap.
"""

from __future__ import annotations

import os
import sqlite3

from langgraph.checkpoint.sqlite import SqliteSaver

from app.ports.checkpoint import CheckpointStore


class SqliteCheckpointStore(CheckpointStore):
    """A durable checkpoint store backed by a SQLite database."""

    def __init__(self, db_path: str = ":memory:") -> None:
        if db_path not in (":memory:", "") and (directory := os.path.dirname(db_path)):
            os.makedirs(directory, exist_ok=True)
        self._conn = sqlite3.connect(db_path or ":memory:", check_same_thread=False)
        self._saver = SqliteSaver(self._conn)

    @classmethod
    def from_db_url(cls, db_url: str) -> SqliteCheckpointStore:
        """Build a store from a ``sqlite:///`` DB URL, sharing the same database file."""
        prefix = "sqlite:///"
        path = db_url[len(prefix) :] if db_url.startswith(prefix) else ":memory:"
        return cls(path)

    def setup(self) -> None:
        self._saver.setup()

    def saver(self) -> object:
        return self._saver
