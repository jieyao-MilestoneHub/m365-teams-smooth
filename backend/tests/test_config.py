"""Settings defaults and env-override for the observability/resilience knobs."""

from __future__ import annotations

from app.config import Settings


def test_observability_defaults_keep_credential_free_demo_unchanged() -> None:
    # _env_file=None isolates from any local backend/.env (runtime kwarg, absent from the stubs).
    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.log_level == "INFO"
    assert settings.log_format == "json"
    assert settings.http_timeout_seconds == 10.0
    assert settings.llm_timeout_seconds == 30.0
    assert settings.graph_timeout_seconds == 60.0
    assert settings.retry_max_attempts == 3
    assert settings.retry_backoff_base_seconds == 0.2
    assert settings.retry_backoff_max_seconds == 2.0
    assert settings.metrics_enabled is True


def test_observability_knobs_are_env_overridable() -> None:
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        log_level="DEBUG",
        log_format="text",
        retry_max_attempts=5,
        metrics_enabled=False,
    )

    assert settings.log_level == "DEBUG"
    assert settings.log_format == "text"
    assert settings.retry_max_attempts == 5
    assert settings.metrics_enabled is False
