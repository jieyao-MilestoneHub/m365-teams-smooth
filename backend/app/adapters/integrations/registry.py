"""Config-driven integration registry: selects real-vs-mock per system from settings."""

from __future__ import annotations

import logging

from app.config import Settings
from app.domain import Capability
from app.domain.errors import ConfigurationError
from app.ports.integration import IntegrationAdapter
from app.ports.registry import IntegrationRegistry

logger = logging.getLogger(__name__)


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

    The requested mode (``FORCE_ALL_MOCK`` → ``"mock"``, else per ``INTEGRATION_MODE``, default
    ``"mock"``) must have a registered adapter. If a non-mock mode was requested but its adapter is
    absent (e.g. ``github:real`` with no ``GITHUB_TOKEN``), we **raise rather than silently serve
    the mock as if it were real** — a configured real capability that cannot be served is a
    fail-fast misconfiguration, never a degradation. A new integration is added by registering its
    real and mock candidates — no edits here.
    """
    modes = settings.integration_modes()
    chosen: list[IntegrationAdapter] = []
    for system, by_mode in candidates.items():
        requested = "mock" if settings.force_all_mock else modes.get(system, "mock")
        adapter = by_mode.get(requested)
        if adapter is None:
            raise ConfigurationError(
                f"integration '{system}' requested mode '{requested}' but no such adapter is "
                f"registered (missing credentials?) — refusing to serve a different mode as if it "
                f"were '{requested}'. Set FORCE_ALL_MOCK or provide the real credentials."
            )
        logger.info("adapter.selected", extra={"system": system, "mode": requested})
        chosen.append(adapter)
    return chosen


def build_registry(
    settings: Settings,
    candidates: dict[str, dict[str, IntegrationAdapter]],
) -> ConfigIntegrationRegistry:
    """Build the registry with adapters selected per config."""
    return ConfigIntegrationRegistry(select_adapters(settings, candidates))
