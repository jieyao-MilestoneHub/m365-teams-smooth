"""Structured logging: a JSON formatter plus an idempotent ``configure_logging``.

A thin stdlib formatter (no structlog/OpenTelemetry dependency — see ADR-0005) that emits one JSON
object per record and captures the ``uvicorn``/``fastapi`` loggers through the same handler.
``configure_logging`` is safe to call repeatedly (startup may invoke it more than once) and honors
the ``log_level`` / ``log_format`` config knobs.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.observability.context import current_context
from app.observability.redact import redact

if TYPE_CHECKING:
    from app.config import Settings

# Attributes the stdlib sets on every record; anything else is caller-supplied ``extra`` to surface.
_RESERVED = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime", "taskName"}

# Marks the handler this module installs so re-configuration replaces it rather than stacking.
_HANDLER_MARKER = "_change_court_handler"


class JsonFormatter(logging.Formatter):
    """Render each record as a single JSON line: timestamp, level, logger, message, plus extras.

    When ``redact_pii`` is set, the message, string-valued extras, and any exception text are masked
    for emails and phone numbers before emission — third-party content reaches log lines and must
    not carry PII.
    """

    def __init__(self, *, redact_pii: bool = True) -> None:
        super().__init__()
        self._redact = redact_pii

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": self.format_timestamp(record),
            "level": record.levelname,
            "logger": record.name,
            "message": self._clean(record.getMessage()),
        }
        payload.update(self.context_fields())
        payload.update({k: self._clean(v) for k, v in _extra_fields(record).items()})
        if record.exc_info:
            payload["exc_info"] = self._clean(self.formatException(record.exc_info))
        return json.dumps(payload, default=str)

    def _clean(self, value: object) -> object:
        """Redact PII from string values; leave non-strings untouched."""
        return redact(value) if self._redact and isinstance(value, str) else value

    def format_timestamp(self, record: logging.LogRecord) -> str:
        """ISO-8601 UTC timestamp with millisecond precision."""
        moment = datetime.fromtimestamp(record.created, tz=UTC)
        return moment.isoformat(timespec="milliseconds")

    def context_fields(self) -> dict[str, object]:
        """Correlation fields (request_id/thread_id/change_id) merged into every record."""
        return dict(current_context())


def _extra_fields(record: logging.LogRecord) -> dict[str, object]:
    """Caller-supplied ``extra={...}`` fields, i.e. record attributes the stdlib did not set."""
    return {key: value for key, value in record.__dict__.items() if key not in _RESERVED}


def _resolve_level(level: str) -> int:
    """Map a config level name (e.g. ``"INFO"``) to its numeric value, defaulting to INFO."""
    resolved = logging.getLevelName(level.upper())
    return resolved if isinstance(resolved, int) else logging.INFO


def _build_formatter(log_format: str, *, redact_pii: bool) -> logging.Formatter:
    if log_format == "text":
        return logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    return JsonFormatter(redact_pii=redact_pii)


def configure_logging(settings: Settings) -> None:
    """Install a single stdout handler on the root logger and route framework loggers through it.

    Idempotent: a prior handler installed by this function is removed before the new one is
    attached, so repeated calls (e.g. from both app factories) leave exactly one handler and honor
    the current ``log_level`` / ``log_format``.
    """
    level = _resolve_level(settings.log_level)
    root = logging.getLogger()

    for existing in list(root.handlers):
        if getattr(existing, _HANDLER_MARKER, False):
            root.removeHandler(existing)

    handler = logging.StreamHandler(stream=sys.stdout)
    setattr(handler, _HANDLER_MARKER, True)
    handler.setFormatter(
        _build_formatter(settings.log_format, redact_pii=settings.log_redaction_enabled)
    )
    root.addHandler(handler)
    root.setLevel(level)

    # Let framework loggers flow through the root handler instead of their own default handlers.
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error", "fastapi"):
        framework = logging.getLogger(name)
        framework.handlers.clear()
        framework.propagate = True
        framework.setLevel(level)
