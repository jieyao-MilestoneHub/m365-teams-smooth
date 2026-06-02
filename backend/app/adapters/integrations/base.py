"""BaseIntegrationAdapter: the template that owns the dry-run branch and error containment.

Subclasses implement small hooks (``_capabilities``, ``_read``, ``_predict``, ``_apply``,
``_fetch_before``, ``_rollback``). The dry-run guarantee (no side effects) lives here once — a
subclass physically cannot run ``_apply`` under DRY_RUN — and every SDK exception is mapped to a
typed ``IntegrationError`` and contained as a FAILED step result, so a single failing step never
crashes a run and never leaks an SDK exception upstream.
"""

from __future__ import annotations

from abc import abstractmethod

from app.domain import (
    Capability,
    ExecutionStep,
    PredictedEffect,
    RequestedAction,
    RollbackHint,
    RunMode,
    StepResult,
    StepStatus,
)
from app.domain.errors import CapabilityNotFoundError, IntegrationError
from app.ports.integration import IntegrationAdapter, ReadQuery, ReadResult


class BaseIntegrationAdapter(IntegrationAdapter):
    """Template-method base for all integration adapters."""

    def capabilities(self) -> list[Capability]:
        return self._capabilities()

    def validate(self, action: RequestedAction) -> None:
        cap = next((c for c in self._capabilities() if c.name == action.capability_name), None)
        if cap is None or cap.system != self.system:
            raise CapabilityNotFoundError(
                f"{self.system}: no capability '{action.capability_name}'"
            )
        required = cap.params_schema.get("required", []) if cap.params_schema else []
        if isinstance(required, list):
            missing = [k for k in required if k not in action.params]
            if missing:
                raise CapabilityNotFoundError(
                    f"{cap.name}: missing required params {missing}"
                )

    def read(self, query: ReadQuery) -> ReadResult:
        try:
            return self._read(query)
        except Exception as exc:  # noqa: BLE001 — boundary: never leak an SDK exception
            raise self._map_error(exc) from exc

    def execute(self, step: ExecutionStep, mode: RunMode) -> StepResult:
        try:
            before = self._fetch_before(step)
        except Exception as exc:  # noqa: BLE001
            return self._failed(step, self._map_error(exc), before=None)
        try:
            if mode is RunMode.DRY_RUN:
                predicted = self._predict(step, before)
                return StepResult(
                    step_id=step.step_id,
                    status=StepStatus.DRY_RUN,
                    before=before,
                    predicted=predicted,
                    rollback=self._rollback(step, before),
                )
            after = self._apply(step)
            return StepResult(
                step_id=step.step_id,
                status=StepStatus.OK,
                before=before,
                after=after,
                rollback=self._rollback(step, before),
            )
        except Exception as exc:  # noqa: BLE001
            return self._failed(step, self._map_error(exc), before=before)

    def fetch_before(self, step: ExecutionStep) -> dict[str, object]:
        return self._fetch_before(step)

    def suggest_rollback(self, step: ExecutionStep, before: dict[str, object]) -> RollbackHint:
        return self._rollback(step, before)

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
