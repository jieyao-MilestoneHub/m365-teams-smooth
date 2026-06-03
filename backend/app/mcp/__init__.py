"""MCP server: tools + resources + OAuth2 resource server (the primary surface).

The MCP server mounts as a separate ASGI sub-app, so the HTTP request-ID middleware does not cover
it. :func:`correlate` binds a fresh ``request_id`` (and the ``thread_id`` a call carries) inside
each tool/resource closure, so MCP-originated trials emit the same correlated stream as HTTP ones.
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any, TypeVar
from uuid import uuid4

from app.observability.context import bind, reset

F = TypeVar("F", bound=Callable[..., Any])


def correlate(func: F) -> F:
    """Bind a per-call ``request_id`` (plus ``thread_id`` when the call carries one) for the call.

    Signature-preserving via ``functools.wraps`` so the MCP server still introspects the original
    parameters when building the tool/resource schema.
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        fields: dict[str, str | None] = {"request_id": uuid4().hex}
        thread_id = kwargs.get("thread_id")
        if isinstance(thread_id, str):
            fields["thread_id"] = thread_id
        tokens = bind(**fields)
        try:
            return func(*args, **kwargs)
        finally:
            reset(tokens)

    return wrapper  # type: ignore[return-value]


__all__ = ["correlate"]
