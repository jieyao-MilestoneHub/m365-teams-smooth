"""The integration registry port: routes a system to its adapter and exposes the merged catalog."""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain import Capability
from app.ports.integration import IntegrationAdapter


class IntegrationRegistry(ABC):
    """Resolves adapters by system and aggregates their capabilities for the intake guard."""

    @abstractmethod
    def get(self, system: str) -> IntegrationAdapter | None:
        """Return the adapter for ``system``, or ``None`` if none is registered."""

    @abstractmethod
    def adapters(self) -> list[IntegrationAdapter]:
        """All registered adapters."""

    @abstractmethod
    def capabilities(self) -> list[Capability]:
        """Every capability across all adapters (the merged catalog)."""
