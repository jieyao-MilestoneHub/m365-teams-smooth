"""Config-driven integration registry: selects real-vs-mock per system from settings."""

from __future__ import annotations

from app.config import Settings
from app.domain import Capability
from app.ports.integration import IntegrationAdapter
from app.ports.registry import IntegrationRegistry


class ConfigIntegrationRegistry(IntegrationRegistry):
    """Holds the selected adapters and resolves them by system."""

    def __init__(self, adapters: list[IntegrationAdapter]) -> None:
        self._by_system: dict[str, IntegrationAdapter] = {a.system: a for a in adapters}

    def get(self, system: str) -> IntegrationAdapter | None:
        return self._by_system.get(system)

    def adapters(self) -> list[IntegrationAdapter]:
        return list(self._by_system.values())

    def capabilities(self) -> list[Capability]:
        return [cap for adapter in self._by_system.values() for cap in adapter.capabilities()]


def select_adapters(
    settings: Settings,
    candidates: dict[str, dict[str, IntegrationAdapter]],
) -> list[IntegrationAdapter]:
    """Choose one adapter per system from ``{system: {mode: adapter}}`` using config.

    ``FORCE_ALL_MOCK`` (or an unknown/missing mode) falls back to the system's ``"mock"`` adapter.
    A new integration is added by registering its real and mock candidates — no edits here.
    """
    modes = settings.integration_modes()
    chosen: list[IntegrationAdapter] = []
    for system, by_mode in candidates.items():
        mode = "mock" if settings.force_all_mock else modes.get(system, "mock")
        adapter = by_mode.get(mode) or by_mode.get("mock")
        if adapter is not None:
            chosen.append(adapter)
    return chosen


def build_registry(
    settings: Settings,
    candidates: dict[str, dict[str, IntegrationAdapter]],
) -> ConfigIntegrationRegistry:
    """Build the registry with adapters selected per config."""
    return ConfigIntegrationRegistry(select_adapters(settings, candidates))
