"""Retention maintenance: finished trials lose their working storage, the audit log never does."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text

from app.adapters.persistence.checkpointer import SqliteCheckpointStore
from app.adapters.persistence.db import make_engine, make_session_factory
from app.adapters.persistence.repositories import SqlAuditRepository, SqlVerdictLedger
from app.config import Settings
from app.container import build_court_service
from app.domain import VerdictType
from app.services.court_service import CourtService
from app.services.maintenance import MaintenanceService
from tests.conftest import ALL_ROLE_DIRECTORY, APPROVER, REQUESTER

_REQ = "slip the launch from 2026-06-10 to 2026-06-17"


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    return f"{tmp_path.as_posix()}/court.db"


@pytest.fixture
def service(db_path: str) -> CourtService:
    return build_court_service(
        Settings(
            force_all_mock=True,
            db_url=f"sqlite:///{db_path}",
            dry_run_default=True,
            approver_directory=ALL_ROLE_DIRECTORY,
        )
    )


def _complete_trial(service: CourtService) -> str:
    """Run one trial through the verdict ledger to completion; returns its thread id.

    Casting through ``cast_verdict`` (rather than the send/decide pair) keeps the verdict-claims
    table populated, so the purge of that working storage stays covered.
    """
    summary = service.submit_change(_REQ, requester=REQUESTER)
    service.cast_verdict(summary.thread_id, VerdictType.APPROVE, principal=APPROVER)
    return summary.thread_id


def _maintenance(db_path: str) -> MaintenanceService:
    db_url = f"sqlite:///{db_path}"
    engine = make_engine(db_url)
    session_factory = make_session_factory(engine)
    store = SqliteCheckpointStore.from_db_url(db_url)
    return MaintenanceService(
        store, SqlAuditRepository(session_factory), SqlVerdictLedger(session_factory)
    )


def _counts(db_path: str) -> tuple[int, int, int]:
    """(checkpoint rows, verdict claims, audit records) in the database file."""
    engine = make_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        checkpoints = conn.execute(text("SELECT count(*) FROM checkpoints")).scalar_one()
        claims = conn.execute(text("SELECT count(*) FROM verdict_claims")).scalar_one()
        audits = conn.execute(text("SELECT count(*) FROM audit_records")).scalar_one()
    return int(checkpoints), int(claims), int(audits)


def test_purge_clears_finished_trials_but_never_audit(
    service: CourtService, db_path: str
) -> None:
    for _ in range(3):
        _complete_trial(service)
    checkpoints, claims, audits = _counts(db_path)
    assert checkpoints > 0 and claims > 0 and audits == 3

    # retention_days=0 → cutoff is "now": everything finished qualifies.
    report = _maintenance(db_path).purge_finished_trials(0)
    assert report.threads_purged == 3

    checkpoints, claims, audits = _counts(db_path)
    assert checkpoints == 0
    assert claims == 0
    assert audits == 3  # the audit log is permanent


def test_purge_keeps_unfinished_and_recent_trials(service: CourtService, db_path: str) -> None:
    _complete_trial(service)
    # Awaiting the requester's review — no audit record yet.
    open_trial = service.submit_change(_REQ, requester=REQUESTER)

    # A generous window: even the finished trial is too recent to purge.
    recent = _maintenance(db_path).purge_finished_trials(30)
    assert recent.threads_purged == 0

    # Cutoff at "now": the finished trial purges, the open one survives untouched.
    report = _maintenance(db_path).purge_finished_trials(0)
    assert report.threads_purged == 1
    assert service.get_status(open_trial.thread_id) is not None
    assert service.get_trial(open_trial.thread_id) is not None


def test_purge_is_idempotent_and_resumable_state_unaffected(
    service: CourtService, db_path: str
) -> None:
    _complete_trial(service)
    maintenance = _maintenance(db_path)
    assert maintenance.purge_finished_trials(0).threads_purged == 1
    # Re-run finds nothing live to purge: the candidate set is the live checkpoint threads.
    assert maintenance.purge_finished_trials(0).threads_purged == 0
