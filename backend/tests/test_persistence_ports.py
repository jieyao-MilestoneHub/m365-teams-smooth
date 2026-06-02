"""The persistence ports' contracts, exercised through small in-memory fakes."""

from __future__ import annotations

import pytest

from app.domain import AuditRecord, Change, ChangeStatus, RunMode, TrialRecord
from app.ports.checkpoint import CheckpointStore
from app.ports.repository import AuditRepository, VerdictLedger


class _MemAudit(AuditRepository):
    def __init__(self) -> None:
        self._records: list[AuditRecord] = []

    def append(self, record: AuditRecord) -> None:
        self._records.append(record)

    def get(self, audit_id: str) -> AuditRecord | None:
        return next((r for r in self._records if r.audit_id == audit_id), None)

    def latest_for_change(self, change_id: str) -> AuditRecord | None:
        matches = [r for r in self._records if r.change_id == change_id]
        return matches[-1] if matches else None


class _MemLedger(VerdictLedger):
    def __init__(self) -> None:
        self._claims: dict[tuple[str, str], str | None] = {}

    def try_claim(self, thread_id: str, idempotency_key: str) -> bool:
        key = (thread_id, idempotency_key)
        if key in self._claims:
            return False
        self._claims[key] = None
        return True

    def mark_completed(self, thread_id: str, idempotency_key: str, audit_id: str) -> None:
        self._claims[(thread_id, idempotency_key)] = audit_id

    def result_for(self, thread_id: str, idempotency_key: str) -> str | None:
        return self._claims.get((thread_id, idempotency_key))


def _record(audit_id: str, change_id: str) -> AuditRecord:
    return AuditRecord(
        audit_id=audit_id,
        change_id=change_id,
        thread_id="t1",
        run_mode=RunMode.DRY_RUN,
        status=ChangeStatus.DONE,
        trial=TrialRecord(change=Change(change_id=change_id, raw_request="x")),
        created_at="2026-06-02T00:00:00Z",
    )


def test_audit_repository_append_and_lookup() -> None:
    repo = _MemAudit()
    repo.append(_record("a1", "c1"))
    repo.append(_record("a2", "c1"))
    assert repo.get("a1") is not None
    assert repo.latest_for_change("c1").audit_id == "a2"  # type: ignore[union-attr]
    assert repo.latest_for_change("missing") is None


def test_verdict_ledger_is_idempotent() -> None:
    ledger = _MemLedger()
    assert ledger.try_claim("t1", "k1") is True
    assert ledger.try_claim("t1", "k1") is False  # second claim rejected -> no re-execution
    ledger.mark_completed("t1", "k1", "a1")
    assert ledger.result_for("t1", "k1") == "a1"


def test_checkpoint_store_is_abstract() -> None:
    with pytest.raises(TypeError):
        CheckpointStore()  # type: ignore[abstract]
