"""BaseIntegrationAdapter retries transient failures per the idempotency rules in ADR-0005."""

from __future__ import annotations

import httpx
import pytest

from app.adapters.integrations.base import BaseIntegrationAdapter
from app.adapters.integrations.retry import (
    RetryClass,
    RetryPolicy,
    is_never_landed,
    is_transient,
)
from app.domain import (
    Capability,
    CapabilityKind,
    CapabilityRef,
    ExecutionStep,
    PredictedEffect,
    RollbackHint,
    RunMode,
    StepStatus,
)
from app.domain.errors import IntegrationError
from app.ports.integration import ReadQuery, ReadResult


def _status_error(code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://example.test")
    response = httpx.Response(code, request=request)
    return httpx.HTTPStatusError("boom", request=request, response=response)


class _RetryProbe(BaseIntegrationAdapter):
    """Adapter that raises a queued sequence of errors on read/apply before succeeding."""

    def __init__(
        self,
        *,
        retry: RetryPolicy,
        cap_name: str = "probe.update_value",
        read_errors: list[Exception] | None = None,
        apply_errors: list[Exception] | None = None,
    ) -> None:
        super().__init__(retry=retry)
        self._cap_name = cap_name
        self._read_errors = read_errors or []
        self._apply_errors = apply_errors or []
        self.read_calls = 0
        self.apply_calls = 0

    @property
    def system(self) -> str:
        return "probe"

    def _capabilities(self) -> list[Capability]:
        return [Capability(system="probe", name=self._cap_name, kind=CapabilityKind.WRITE)]

    def _read(self, query: ReadQuery) -> ReadResult:
        self.read_calls += 1
        if self._read_errors:
            raise self._read_errors.pop(0)
        return ReadResult(capability=query.capability, data={"ok": True})

    def _predict(self, step: ExecutionStep, before: dict[str, object]) -> PredictedEffect:
        return PredictedEffect(summary="would set")

    def _apply(self, step: ExecutionStep) -> dict[str, object]:
        self.apply_calls += 1
        if self._apply_errors:
            raise self._apply_errors.pop(0)
        return {"done": True}

    def _fetch_before(self, step: ExecutionStep) -> dict[str, object]:
        return {}

    def _rollback(self, step: ExecutionStep, before: dict[str, object]) -> RollbackHint:
        return RollbackHint(step_id=step.step_id, system="probe", instruction="restore")


def _policy(max_attempts: int = 3) -> tuple[RetryPolicy, list[float], list[str]]:
    sleeps: list[float] = []
    metrics: list[str] = []
    policy = RetryPolicy(
        max_attempts=max_attempts,
        base_seconds=0.01,
        max_seconds=0.05,
        sleep=sleeps.append,
        metrics=metrics.append,
    )
    return policy, sleeps, metrics


def _step(cap_name: str) -> ExecutionStep:
    return ExecutionStep(step_id="s1", capability=CapabilityRef(system="probe", name=cap_name))


# --- classifiers -----------------------------------------------------------


def test_never_landed_is_connection_class_only() -> None:
    assert is_never_landed(httpx.ConnectError("x")) is True
    assert is_never_landed(httpx.ConnectTimeout("x")) is True
    assert is_never_landed(httpx.ReadTimeout("x")) is False  # may have landed
    assert is_never_landed(_status_error(503)) is False


def test_transient_covers_timeouts_and_retryable_statuses() -> None:
    assert is_transient(httpx.ConnectError("x")) is True
    assert is_transient(httpx.ReadTimeout("x")) is True
    assert is_transient(_status_error(503)) is True
    assert is_transient(_status_error(429)) is True
    assert is_transient(_status_error(404)) is False  # client error: not retryable


# --- read (LIBERAL) --------------------------------------------------------


def test_read_retries_transient_then_succeeds() -> None:
    policy, sleeps, metrics = _policy(max_attempts=3)
    probe = _RetryProbe(retry=policy, read_errors=[httpx.ReadTimeout("blip")])

    result = probe.read(ReadQuery(capability="probe.read_value"))

    assert result.data == {"ok": True}
    assert probe.read_calls == 2  # failed once, retried once
    assert metrics == ["integration.retries"]
    assert len(sleeps) == 1 and 0 < sleeps[0] <= policy.max_seconds


def test_read_exhausts_attempts_and_raises_mapped_error() -> None:
    policy, _sleeps, _metrics = _policy(max_attempts=2)
    probe = _RetryProbe(retry=policy, read_errors=[httpx.ReadTimeout("a"), httpx.ReadTimeout("b")])

    with pytest.raises(IntegrationError):
        probe.read(ReadQuery(capability="probe.read_value"))
    assert probe.read_calls == 2  # bounded by max_attempts


def test_disabled_policy_never_retries() -> None:
    probe = _RetryProbe(retry=RetryPolicy.disabled(), read_errors=[httpx.ReadTimeout("blip")])
    with pytest.raises(IntegrationError):
        probe.read(ReadQuery(capability="probe.read_value"))
    assert probe.read_calls == 1


# --- write (idempotency-classified) ---------------------------------------


def test_create_retries_only_on_never_landed() -> None:
    # A connection failure proves the create never landed → safe to retry.
    policy, _s, _m = _policy(max_attempts=3)
    probe = _RetryProbe(
        retry=policy, cap_name="probe.create_thing", apply_errors=[httpx.ConnectError("down")]
    )
    result = probe.execute(_step("probe.create_thing"), RunMode.LIVE)
    assert result.status is StepStatus.OK
    assert probe.apply_calls == 2


def test_create_does_not_retry_on_post_send_timeout() -> None:
    # A read timeout might mean the create landed → must NOT retry.
    policy, _s, _m = _policy(max_attempts=3)
    probe = _RetryProbe(
        retry=policy, cap_name="probe.create_thing", apply_errors=[httpx.ReadTimeout("late")]
    )
    result = probe.execute(_step("probe.create_thing"), RunMode.LIVE)
    assert result.status is StepStatus.FAILED  # contained, not retried
    assert probe.apply_calls == 1


def test_update_retries_liberally() -> None:
    # An update_* is idempotent → retry even a post-send timeout.
    policy, _s, _m = _policy(max_attempts=3)
    probe = _RetryProbe(
        retry=policy, cap_name="probe.update_thing", apply_errors=[httpx.ReadTimeout("late")]
    )
    result = probe.execute(_step("probe.update_thing"), RunMode.LIVE)
    assert result.status is StepStatus.OK
    assert probe.apply_calls == 2


def test_retry_class_for_step_follows_naming_convention() -> None:
    probe = _RetryProbe(retry=RetryPolicy.disabled())
    assert probe._retry_class_for(_step("probe.update_value")) is RetryClass.LIBERAL
    assert probe._retry_class_for(_step("probe.create_value")) is RetryClass.NEVER_LANDED
    assert probe._retry_class_for(_step("probe.comment_value")) is RetryClass.NEVER_LANDED


def test_backoff_is_bounded_by_max_seconds() -> None:
    policy, _s, _m = _policy(max_attempts=5)
    for attempt in range(1, 6):
        delay = policy.backoff(attempt)
        assert 0 < delay <= policy.max_seconds
