"""Input-safety verdict: the result of screening untrusted content before it reaches the model."""

from __future__ import annotations

from pydantic import BaseModel, Field

# Provenance of a verdict, so callers and the UI can label it honestly.
SOURCE_HEURISTIC = "heuristic"
SOURCE_AZURE_PROMPT_SHIELDS = "azure-prompt-shields"
SOURCE_UNAVAILABLE = "unavailable"


class ShieldVerdict(BaseModel):
    """Whether screened input looks like a prompt-injection / jailbreak attempt."""

    flagged: bool = False
    categories: list[str] = Field(default_factory=list)
    source: str = SOURCE_HEURISTIC
