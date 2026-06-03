"""Correlation context: request/thread/change IDs carried via ``contextvars``.

These cross-cutting IDs must appear on every log line without polluting call signatures, so they
live in async-safe ``contextvars`` rather than being threaded through every node/service/adapter
call. The formatter merges :func:`current_context` into each record; the HTTP middleware and the
MCP/node entry points bind the values.
"""

from __future__ import annotations

from contextvars import ContextVar, Token

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_thread_id: ContextVar[str | None] = ContextVar("thread_id", default=None)
_change_id: ContextVar[str | None] = ContextVar("change_id", default=None)

_VARS: dict[str, ContextVar[str | None]] = {
    "request_id": _request_id,
    "thread_id": _thread_id,
    "change_id": _change_id,
}


def bind(**fields: str | None) -> dict[str, Token[str | None]]:
    """Bind correlation fields for the current context, returning reset tokens keyed by field name.

    Pass the returned mapping to :func:`reset` to restore the prior values (e.g. in a ``finally``).
    """
    tokens: dict[str, Token[str | None]] = {}
    for name, value in fields.items():
        var = _VARS.get(name)
        if var is None:
            raise KeyError(f"unknown correlation field: {name}")
        tokens[name] = var.set(value)
    return tokens


def reset(tokens: dict[str, Token[str | None]]) -> None:
    """Restore the context vars to the values captured before the matching :func:`bind`."""
    for name, token in tokens.items():
        _VARS[name].reset(token)


def current_context() -> dict[str, str]:
    """The correlation fields currently set (non-``None``), for merging into a log record."""
    out: dict[str, str] = {}
    for name, var in _VARS.items():
        value = var.get()
        if value is not None:
            out[name] = value
    return out
