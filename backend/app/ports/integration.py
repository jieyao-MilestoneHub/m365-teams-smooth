"""The integration port: the single boundary between the court and any external system.

Concrete adapters (real GitHub, mock others) implement :class:`IntegrationAdapter`; the agent and
services depend on this interface only, never on an integration SDK. Capabilities split into
**read** (evidence for the impact node) and **write** (actions for execution). Adapters stay
ignorant of the policy tag vocabulary — translating read results into tagged evidence is the impact
node's responsibility.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel, Field

from app.domain import (
    Capability,
    ExecutionStep,
    RequestedAction,
    RollbackHint,
    RunMode,
    StepResult,
)


class ReadQuery(BaseModel):
    """A request to a read capability."""

    capability: str
    params: dict[str, object] = Field(default_factory=dict)


class ReadResult(BaseModel):
    """The raw data a read capability returns. The impact node shapes this into evidence + tags."""

    capability: str
    data: dict[str, object] = Field(default_factory=dict)


class IntegrationAdapter(ABC):
    """One external system the court can read from and write to."""

    @property
    @abstractmethod
    def system(self) -> str:
        """The system key this adapter serves (e.g. ``"github"``)."""

    @abstractmethod
    def capabilities(self) -> list[Capability]:
        """The read and write capabilities this adapter registers."""

    @abstractmethod
    def validate(self, action: RequestedAction) -> None:
        """Raise ``CapabilityNotFoundError`` if the action is unsupported or its params invalid."""

    @abstractmethod
    def read(self, query: ReadQuery) -> ReadResult:
        """Run a read capability and return its raw data (no side effects)."""

    @abstractmethod
    def execute(self, step: ExecutionStep, mode: RunMode) -> StepResult:
        """Run a write step. In ``DRY_RUN`` mode, predict the effect without mutating anything."""

    @abstractmethod
    def fetch_before(self, step: ExecutionStep) -> dict[str, object]:
        """Snapshot the target state before a write, for the audit before/after record."""

    @abstractmethod
    def suggest_rollback(self, step: ExecutionStep, before: dict[str, object]) -> RollbackHint:
        """Produce an advisory rollback hint for a write step. Never auto-executed."""
