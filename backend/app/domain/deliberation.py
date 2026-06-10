"""The agent's deliberation: an append-only reasoning trace, one entry per court node.

Pure domain — imports only pydantic. Each ``DeliberationEntry`` records why a node reached its
conclusion (the LLM's reasoning when one is configured, an honest offline stub otherwise), so the
run page, the Adaptive Card, and the MCP trial resource can show the chain of reasoning, not just
the final structured outputs. The trace is append-only and never affects risk, quorum, or verdict.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

# Provenance of an entry's reasoning text, so the UI can label it honestly.
SOURCE_LLM = "llm"
SOURCE_OFFLINE_STUB = "offline-stub"


class DeliberationEntry(BaseModel):
    """One node's reasoning for the conclusion it reached."""

    node: str  # intake | impact | options | policy | verify
    role: str = ""  # prosecutor | defender | "" — mirrors the courtroom roles
    rationale: str
    source: str = SOURCE_LLM  # SOURCE_LLM | SOURCE_OFFLINE_STUB


class Deliberation(BaseModel):
    """The ordered, append-only reasoning trace for a trial."""

    entries: list[DeliberationEntry] = Field(default_factory=list)
