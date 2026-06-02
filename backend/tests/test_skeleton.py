"""Smoke tests for the walking skeleton: the app boots and settings parse."""

from __future__ import annotations

import pytest
from fastapi import FastAPI

from app.config import Settings
from app.main import create_app


def test_create_app_returns_configured_app() -> None:
    app = create_app(Settings())
    assert isinstance(app, FastAPI)
    assert app.title == "AI Change Court"


def test_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("DRY_RUN_DEFAULT", "FORCE_ALL_MOCK", "DB_URL", "INTEGRATION_MODE"):
        monkeypatch.delenv(var, raising=False)
    settings = Settings()
    assert settings.dry_run_default is True
    assert settings.force_all_mock is False
    assert settings.db_url.startswith("sqlite")


def test_integration_modes_parses_pairs() -> None:
    settings = Settings(integration_mode="github:real, outlook:mock")
    assert settings.integration_modes() == {"github": "real", "outlook": "mock"}


def test_force_all_mock_overrides_modes() -> None:
    settings = Settings(integration_mode="github:real", force_all_mock=True)
    assert settings.integration_modes() == {"github": "mock"}
