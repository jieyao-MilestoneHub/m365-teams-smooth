"""The checkpoint store port: makes the LangGraph saver swappable (SQLite now, Postgres later).

This port deliberately does not name a LangGraph type, so ``ports/`` carries no graph-engine
dependency. The concrete adapter (in ``adapters/persistence/``) returns the real saver and is the
only place the saver type appears; the graph builder accepts it opaquely.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class CheckpointStore(ABC):
    """Provides the checkpoint saver the court graph compiles against."""

    @abstractmethod
    def setup(self) -> None:
        """Initialize backing storage (e.g. create checkpoint tables) if needed."""

    @abstractmethod
    def saver(self) -> object:
        """Return the underlying checkpoint saver instance used to compile the graph."""
