"""Terminal outcomes are recorded truthfully and leave no zombie queue rows.

Integration tests over the real graph + SQL stores — the layer where the audit record, the
precedent, and the pending index actually meet, which fakes-based unit tests cannot cover.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.adapters.persistence.checkpointer import SqliteCheckpointStore
from app.adapters.persistence.db import make_engine, make_session_factory
from app.adapters.persistence.repositories import (
    SqlApprovalLedger,
    SqlAuditRepository,
    SqlPrecedentStore,
    SqlVerdictLedger,
)
from app.config import Settings
from app.container import build_court_service
from app.domain import ChangeStatus, Principal, VerdictType
from app.services.court_service import CourtService
from app.services.maintenance import MaintenanceService

REQUESTER = Principal(oid="low-1", upn="low@x")
APPROVER = Principal(oid="app-1", upn="approver@x")

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
            approver_directory="eng_lead:approver@x,comms:approver@x",
        )
    )


def _audit_repo(db_path: str) -> SqlAuditRepository:
    return SqlAuditRepository(make_session_factory(make_engine(f"sqlite:///{db_path}")))


def _ledger(service: CourtService) -> SqlApprovalLedger:
    ledger = service._approvals  # white-box: assert the read-model
    assert isinstance(ledger, SqlApprovalLedger)
    return ledger


def test_rejected_trial_audit_and_precedent_record_rejected(
    service: CourtService, db_path: str
) -> None:
    s = service.submit_change(_REQ, requester=REQUESTER)
    service.send_for_approval(s.thread_id, actor=REQUESTER, note="ready")
    rejected = service.decide(s.thread_id, actor=APPROVER, approve=False, note="not yet")
    assert rejected.status == ChangeStatus.REJECTED.value

    audit = _audit_repo(db_path).latest_for_change(s.change_id)
    assert audit is not None
    assert audit.status is ChangeStatus.REJECTED  # the permanent record, not a generic DONE

    session_factory = make_session_factory(make_engine(f"sqlite:///{db_path}"))
    precedents = SqlPrecedentStore(session_factory).find_similar(
        "launch", ["schedule.milestone_move"], top_k=5
    )
    assert any(p.thread_id == s.thread_id and p.status == "rejected" for p in precedents)


def test_withdrawn_trial_audit_records_withdrawn(service: CourtService, db_path: str) -> None:
    s = service.submit_change(_REQ, requester=REQUESTER)
    service.withdraw_change(s.thread_id, actor=REQUESTER)

    audit = _audit_repo(db_path).latest_for_change(s.change_id)
    assert audit is not None
    assert audit.status is ChangeStatus.WITHDRAWN


def test_legacy_cast_verdict_clears_the_pending_index(service: CourtService) -> None:
    s = service.submit_change(_REQ, requester=REQUESTER)
    service.send_for_approval(s.thread_id, actor=REQUESTER, note="ready")
    ledger = _ledger(service)
    assert s.thread_id in ledger.pending_thread_ids()

    # The legacy verdict path bypasses decide(); it must still clean the queue.
    result = service.cast_verdict(s.thread_id, VerdictType.APPROVE)
    assert result.status == ChangeStatus.DONE.value
    assert s.thread_id not in ledger.pending_thread_ids()


def test_purge_clears_a_leaked_pending_row(service: CourtService, db_path: str) -> None:
    # Finish a trial, then simulate a leaked queue row for it (the pre-fix cast_verdict bug).
    s = service.submit_change(_REQ)
    service.cast_verdict(s.thread_id, VerdictType.APPROVE)
    ledger = _ledger(service)
    ledger.mark_pending(s.thread_id, "2026-06-04T00:00:00+00:00")
    assert s.thread_id in ledger.pending_thread_ids()

    db_url = f"sqlite:///{db_path}"
    session_factory = make_session_factory(make_engine(db_url))
    maintenance = MaintenanceService(
        SqliteCheckpointStore.from_db_url(db_url),
        SqlAuditRepository(session_factory),
        SqlVerdictLedger(session_factory),
        approvals=SqlApprovalLedger(session_factory),
    )
    report = maintenance.purge_finished_trials(0)
    assert report.threads_purged == 1
    assert s.thread_id not in ledger.pending_thread_ids()


def test_find_similar_with_empty_subject_returns_nothing(db_path: str) -> None:
    session_factory = make_session_factory(make_engine(f"sqlite:///{db_path}"))
    from app.adapters.persistence.db import init_db

    init_db(make_engine(f"sqlite:///{db_path}"))
    store = SqlPrecedentStore(session_factory)
    from app.ports.memory import PrecedentRecord

    store.record(PrecedentRecord(thread_id="t1", subject="", created_at="2026-06-01T00:00:00Z"))
    assert store.find_similar("", [], top_k=5) == []
