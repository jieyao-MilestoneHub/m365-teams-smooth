"""The SQLite repositories: append-only audit and exactly-once verdict ledger."""

from __future__ import annotations

import pytest

from app.adapters.persistence.db import init_db, make_engine, make_session_factory
from app.adapters.persistence.repositories import SqlAuditRepository, SqlVerdictLedger
from app.domain import AuditRecord, Change, ChangeStatus, RunMode, TrialRecord


@pytest.fixture
def session_factory():  # type: ignore[no-untyped-def]
    engine = make_engine("sqlite:///:memory:")
    init_db(engine)
    return make_session_factory(engine)


def _record(audit_id: str, change_id: str, created_at: str) -> AuditRecord:
    return AuditRecord(
        audit_id=audit_id,
        change_id=change_id,
        thread_id="t1",
        run_mode=RunMode.DRY_RUN,
        status=ChangeStatus.DONE,
        trial=TrialRecord(change=Change(change_id=change_id, raw_request="x")),
        created_at=created_at,
    )


def test_audit_append_get_and_latest(session_factory) -> None:  # type: ignore[no-untyped-def]
    repo = SqlAuditRepository(session_factory)
    repo.append(_record("a1", "c1", "2026-06-02T00:00:00Z"))
    repo.append(_record("a2", "c1", "2026-06-02T01:00:00Z"))

    assert repo.get("a1") is not None
    assert repo.get("a1").run_mode is RunMode.DRY_RUN  # type: ignore[union-attr]
    assert repo.latest_for_change("c1").audit_id == "a2"  # type: ignore[union-attr]
    assert repo.latest_for_change("missing") is None


def test_verdict_ledger_claim_is_exactly_once(session_factory) -> None:  # type: ignore[no-untyped-def]
    ledger = SqlVerdictLedger(session_factory)
    assert ledger.try_claim("t1", "k1") is True
    assert ledger.try_claim("t1", "k1") is False  # duplicate rejected
    assert ledger.try_claim("t1", "k2") is True  # different key allowed

    ledger.mark_completed("t1", "k1", "a1")
    assert ledger.result_for("t1", "k1") == "a1"
    assert ledger.result_for("t1", "k2") is None
