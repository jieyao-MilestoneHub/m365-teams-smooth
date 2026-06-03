"""Cross-cutting observability: structured logging, correlation, and metrics.

This package is a single-implementation module, not a ``ports/`` abstraction — there is only ever
one logger/registry, so modules call ``logging.getLogger(__name__)`` directly (see ADR-0005). It is
the home for concerns that span the HTTP edge, the MCP edge, and the graph nodes.
"""

from __future__ import annotations

from app.observability.logging import JsonFormatter, configure_logging

__all__ = ["JsonFormatter", "configure_logging"]
