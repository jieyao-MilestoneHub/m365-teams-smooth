"""BaseIntegrationAdapter: the template that owns the dry-run branch and error containment.

Subclasses implement small hooks (``_capabilities``, ``_read``, ``_predict``, ``_apply``,
``_fetch_before``, ``_rollback``). The dry-run guarantee (no side effects) lives here once — a
subclass physically cannot run ``_apply`` under DRY_RUN — and every SDK exception is mapped to a
typed ``IntegrationError`` and contained as a FAILED step result, so a single failing step never
crashes a run and never leaks an SDK exception upstream.
"""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import Callable
from typing import TypeVar

from app.adapters.integrations.retry import RetryClass, RetryPolicy
from app.domain import (
    Capability,
    ExecutionStep,
    PredictedEffect,
    RequestedAction,
    RollbackHint,
    RunMode,
    StepResult,
    StepStatus,
    param_violations,
)
from app.domain.errors import CapabilityNotFoundError, IntegrationError
from app.ports.integration import IntegrationAdapter, ReadQuery, ReadResult

T = TypeVar("T")


class BaseIntegrationAdapter(IntegrationAdapter):
    """Template-method base for all integration adapters."""

    # Adapters that do real I/O receive a config-driven policy; mocks keep this disabled default.
    _retry: RetryPolicy = RetryPolicy.disabled()
    # Read-only-real adapters read live data but never mutate; a LIVE write against one degrades to
    # a predicted effect (as a dry-run would) instead of failing the run. Default: writes apply.
    _writes_enabled: bool = True

    def __init__(self, *, retry: RetryPolicy | None = None) -> None:
        if retry is not None:
            self._retry = retry

    def capabilities(self) -> list[Capability]:
        return self._capabilities()

    def validate(self, action: RequestedAction) -> None:
        cap = next((c for c in self._capabilities() if c.name == action.capability_name), None)
        if cap is None or cap.system != self.system:
            raise CapabilityNotFoundError(
                f"{self.system}: no capability '{action.capability_name}'"
            )
        violations = param_violations(cap, action.params)
        if violations:
            raise CapabilityNotFoundError(f"{cap.name}: {'; '.join(violations)}")

    def read(self, query: ReadQuery) -> ReadResult:
        # Reads are idempotent — retry any transient error.
        try:
            return self._with_retry(lambda: self._read(query), RetryClass.LIBERAL)
        except Exception as exc:  # noqa: BLE001 — boundary: never leak an SDK exception
            raise self._map_error(exc) from exc

    def execute(self, step: ExecutionStep, mode: RunMode) -> StepResult:
        try:
            before = self._with_retry(lambda: self._fetch_before(step), RetryClass.LIBERAL)
        except Exception as exc:  # noqa: BLE001
            return self._failed(step, self._map_error(exc), before=None)
        try:
            if mode is RunMode.DRY_RUN or not self._writes_enabled:
                # A dry-run — or any write against a read-only-real adapter — predicts only, with no
                # side effects, so retry liberally.
                predicted = self._with_retry(
                    lambda: self._predict(step, before), RetryClass.LIBERAL
                )
                return StepResult(
                    step_id=step.step_id,
                    status=StepStatus.DRY_RUN,
                    before=before,
                    predicted=predicted,
                    rollback=self._rollback(step, before),
                )
            # A LIVE write retries only as far as its idempotency allows.
            after = self._with_retry(lambda: self._apply(step), self._retry_class_for(step))
            return StepResult(
                step_id=step.step_id,
                status=StepStatus.OK,
                before=before,
                after=after,
                resource_url=self._resource_url(after),
                rollback=self._rollback(step, before),
            )
        except Exception as exc:  # noqa: BLE001
            return self._failed(step, self._map_error(exc), before=before)

    def fetch_before(self, step: ExecutionStep) -> dict[str, object]:
        return self._fetch_before(step)

    def suggest_rollback(self, step: ExecutionStep, before: dict[str, object]) -> RollbackHint:
        return self._rollback(step, before)

    # --- retry -------------------------------------------------------------
    def _with_retry(self, call: Callable[[], T], retry_class: RetryClass) -> T:
        """Run ``call``, retrying transient failures per ``retry_class`` and the policy's backoff.

        Runs before :meth:`_map_error` so the original SDK exception type stays visible to the
        retry classifier.
        """
        attempt = 1
        while True:
            try:
                return call()
            except Exception as exc:  # noqa: BLE001 — classified, then retried or re-raised
                if attempt >= self._retry.max_attempts or not self._retry.should_retry(
                    exc, retry_class
                ):
                    raise
                self._retry.metrics("integration.retries")
                self._retry.sleep(self._retry.backoff(attempt))
                attempt += 1

    def _retry_class_for(self, step: ExecutionStep) -> RetryClass:
        """The retry class for a LIVE write, inferred from the capability naming convention.

        ``update_*`` is idempotent (retry liberally); ``create_*`` / ``comment_*`` are not, so they
        retry only when the request provably never landed. Unknown writes take the safe default.
        """
        name = step.capability.name
        if ".update_" in name:
            return RetryClass.LIBERAL
        return RetryClass.NEVER_LANDED

    # --- error containment -------------------------------------------------
    def _map_error(self, exc: Exception) -> IntegrationError:
        if isinstance(exc, IntegrationError):
            return exc
        return IntegrationError(f"{self.system}: {exc}")

    def _failed(
        self, step: ExecutionStep, error: IntegrationError, *, before: dict[str, object] | None
    ) -> StepResult:
        rollback: RollbackHint | None = None
        if before is not None:
            try:
                rollback = self._rollback(step, before)
            except Exception:  # noqa: BLE001 — rollback hint is best-effort
                rollback = None
        return StepResult(
            step_id=step.step_id,
            status=StepStatus.FAILED,
            before=before,
            error=str(error),
            rollback=rollback,
        )

    # --- resource link -----------------------------------------------------
    _URL_KEYS = ("html_url", "webUrl", "webLink", "url")

    def _resource_url(self, after: dict[str, object]) -> str | None:
        """A web link to the modified resource, if the after-state carries one. Scans the top level
        and one level into nested objects (e.g. ``after['milestone']['html_url']``)."""

        def _link_in(obj: dict[str, object]) -> str | None:
            for key in self._URL_KEYS:
                value = obj.get(key)
                if isinstance(value, str) and value.startswith("http"):
                    return value
            return None

        direct = _link_in(after)
        if direct is not None:
            return direct
        for value in after.values():
            if isinstance(value, dict):
                nested = _link_in(value)
                if nested is not None:
                    return nested
        return None

    # --- subclass hooks ----------------------------------------------------
    @abstractmethod
    def _capabilities(self) -> list[Capability]: ...

    @abstractmethod
    def _read(self, query: ReadQuery) -> ReadResult: ...

    @abstractmethod
    def _predict(self, step: ExecutionStep, before: dict[str, object]) -> PredictedEffect: ...

    @abstractmethod
    def _apply(self, step: ExecutionStep) -> dict[str, object]: ...

    @abstractmethod
    def _fetch_before(self, step: ExecutionStep) -> dict[str, object]: ...

    @abstractmethod
    def _rollback(self, step: ExecutionStep, before: dict[str, object]) -> RollbackHint: ...
