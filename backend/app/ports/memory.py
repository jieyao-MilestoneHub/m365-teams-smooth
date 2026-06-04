"""Precedent memory port: past rulings inform the agentic roles' reasoning on new trials.

A precedent is a compact, queryable summary of a finished trial — never the working state. The
default store keeps precedents in the court's own database with explainable retrieval (same
subject, ranked by tag overlap), because in a governance setting "why was this precedent cited"
must have a concrete answer. A semantic-search store can replace it behind this port.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel, Field


class PrecedentRecord(BaseModel):
    """One past ruling, summarized for retrieval into future trials."""

    thread_id: str
    subject: str = ""
    tags: list[str] = Field(default_factory=list)
    raw_request: str = ""
    verdict_type: str = ""
    plan_kind: str = ""
    rationale: str = ""
    status: str = ""
    created_at: str = ""


class MemoryPort(ABC):
    """Records finished trials and retrieves the most relevant precedents for a new one."""

    @abstractmethod
    def record(self, record: PrecedentRecord) -> None:
        """Store a finished trial's precedent summary."""

    @abstractmethod
    def find_similar(
        self, subject: str, tags: list[str], *, top_k: int = 3
    ) -> list[PrecedentRecord]:
        """The ``top_k`` precedents sharing the subject, ranked by tag overlap then recency."""
