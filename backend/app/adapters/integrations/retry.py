"""Idempotency-aware retry for the integration adapters.

A transient network blip should not fail a whole trial, but a non-idempotent write must never be
retried once the request might have reached the server — a second attempt could create a duplicate
issue or comment. So retries are classified (ADR-0005):

- **reads, dry-run predictions, and idempotent ``update_*`` writes** retry on any transient error;
- **non-idempotent ``create_*`` / ``comment_*`` writes** retry *only* on connection-class failures
  that prove the request never landed (never on an HTTP status or a post-send read timeout).

The policy is config-driven and emits a no-op-safe ``metrics`` hook on each retry.
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum, auto
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from app.config import Settings

# Server-side statuses worth retrying for an idempotent call (rate limit + transient 5xx).
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def is_never_landed(exc: BaseException) -> bool:
    """True only when the request provably never reached the server, so a retry cannot double-apply.

    Connection establishment failures qualify; a read/write timeout or any received HTTP status does
    not — by then the request may already have been processed.
    """
    return isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout, ConnectionError))


def is_transient(exc: BaseException) -> bool:
    """True for blips safe to retry on an idempotent call (a read, a dry-run, an ``update_*``)."""
    if is_never_landed(exc):
        return True
    if isinstance(exc, (httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout, TimeoutError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in _RETRYABLE_STATUS
    return False


class RetryClass(Enum):
    """How aggressively a given call may be retried."""

    NONE = auto()
    NEVER_LANDED = auto()  # non-idempotent writes: retry only if the request never landed
    LIBERAL = auto()  # reads / dry-run / idempotent writes: retry any transient error


_PREDICATES: dict[RetryClass, Callable[[BaseException], bool]] = {
    RetryClass.NONE: lambda _exc: False,
    RetryClass.NEVER_LANDED: is_never_landed,
    RetryClass.LIBERAL: is_transient,
}


def _noop_metric(_name: str) -> None:
    """Default metrics sink — does nothing until a registry is wired in."""


@dataclass(frozen=True)
class RetryPolicy:
    """Bounded exponential backoff with jitter, gated by a per-call :class:`RetryClass`."""

    max_attempts: int = 1
    base_seconds: float = 0.2
    max_seconds: float = 2.0
    sleep: Callable[[float], None] = time.sleep
    metrics: Callable[[str], None] = _noop_metric

    @classmethod
    def disabled(cls) -> RetryPolicy:
        """A single-attempt policy — the safe default for adapters that do no real I/O (mocks)."""
        return cls(max_attempts=1)

    @classmethod
    def from_settings(
        cls, settings: Settings, *, metrics: Callable[[str], None] | None = None
    ) -> RetryPolicy:
        """Build the policy from the retry config knobs."""
        return cls(
            max_attempts=settings.retry_max_attempts,
            base_seconds=settings.retry_backoff_base_seconds,
            max_seconds=settings.retry_backoff_max_seconds,
            metrics=metrics or _noop_metric,
        )

    def should_retry(self, exc: BaseException, retry_class: RetryClass) -> bool:
        """Whether ``exc`` is retryable under ``retry_class``."""
        return _PREDICATES[retry_class](exc)

    def backoff(self, attempt: int) -> float:
        """Jittered exponential wait before retry ``attempt`` (1-based), capped at ``max_seconds``.

        Jitter is 50–100% of the capped delay, so the returned value never exceeds ``max_seconds``.
        """
        delay = min(self.base_seconds * (2 ** (attempt - 1)), self.max_seconds)
        return float(delay * (0.5 + 0.5 * random.random()))
