"""Structured logging core: JSON formatter shape and idempotent ``configure_logging``."""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Iterator

import pytest

from app.config import Settings
from app.observability.logging import _HANDLER_MARKER, JsonFormatter, configure_logging


def _settings(**overrides: object) -> Settings:
    # _env_file=None isolates from any local backend/.env (runtime kwarg, absent from the stubs).
    return Settings(_env_file=None, **overrides)  # type: ignore[call-arg, arg-type]


def _record(**extra: object) -> logging.LogRecord:
    return logging.makeLogRecord(
        {"name": "app.test", "levelno": logging.INFO, "levelname": "INFO", "msg": "hello", **extra}
    )


@pytest.fixture
def restore_root_logger() -> Iterator[None]:
    """Snapshot and restore the root logger so configure_logging tests do not leak global state."""
    root = logging.getLogger()
    saved_handlers = root.handlers[:]
    saved_level = root.level
    yield
    root.handlers[:] = saved_handlers
    root.setLevel(saved_level)


def _our_handlers() -> list[logging.Handler]:
    return [h for h in logging.getLogger().handlers if getattr(h, _HANDLER_MARKER, False)]


def test_json_formatter_emits_required_fields() -> None:
    payload = json.loads(JsonFormatter().format(_record()))

    assert payload["level"] == "INFO"
    assert payload["logger"] == "app.test"
    assert payload["message"] == "hello"
    assert "timestamp" in payload


def test_json_formatter_surfaces_extra_fields() -> None:
    payload = json.loads(JsonFormatter().format(_record(thread_id="t1", step_id="s1")))

    assert payload["thread_id"] == "t1"
    assert payload["step_id"] == "s1"


def test_json_formatter_includes_exception() -> None:
    try:
        raise ValueError("boom")
    except ValueError:
        record = logging.LogRecord(
            "app.test", logging.ERROR, __file__, 1, "failed", None, sys.exc_info()
        )

    payload = json.loads(JsonFormatter().format(record))

    assert "ValueError: boom" in payload["exc_info"]


def test_context_fields_are_empty_until_correlation_lands() -> None:
    # The merge point exists now; contextvars populate it in #184.
    assert JsonFormatter().context_fields() == {}


def test_configure_logging_installs_single_json_handler(restore_root_logger: None) -> None:
    configure_logging(_settings())

    handlers = _our_handlers()
    assert len(handlers) == 1
    assert isinstance(handlers[0].formatter, JsonFormatter)


def test_configure_logging_is_idempotent(restore_root_logger: None) -> None:
    configure_logging(_settings())
    configure_logging(_settings())

    assert len(_our_handlers()) == 1


def test_configure_logging_honors_level_and_text_format(restore_root_logger: None) -> None:
    configure_logging(_settings(log_level="WARNING", log_format="text"))

    assert logging.getLogger().level == logging.WARNING
    assert not isinstance(_our_handlers()[0].formatter, JsonFormatter)


def test_configure_logging_routes_framework_loggers(restore_root_logger: None) -> None:
    configure_logging(_settings())

    for name in ("uvicorn", "uvicorn.access", "uvicorn.error", "fastapi"):
        framework = logging.getLogger(name)
        assert framework.handlers == []
        assert framework.propagate is True


def test_emitted_record_is_json_with_extras(
    restore_root_logger: None, capsys: pytest.CaptureFixture[str]
) -> None:
    configure_logging(_settings())
    logging.getLogger("app.demo").info("hi", extra={"change_id": "c1"})

    line = capsys.readouterr().out.strip().splitlines()[-1]
    payload = json.loads(line)
    assert payload["message"] == "hi"
    assert payload["change_id"] == "c1"
