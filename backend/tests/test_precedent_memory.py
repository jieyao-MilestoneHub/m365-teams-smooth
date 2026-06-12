"""Precedent memory: explainable retrieval, audit-side recording, and prompt injection."""

from __future__ import annotations

from app.adapters.persistence.db import make_engine, make_session_factory
from app.adapters.persistence.repositories import SqlPrecedentStore
from app.agent.agentic.precedents import render_precedents
from app.config import Settings
from app.container import build_court_service
from app.ports.memory import MemoryPort, PrecedentRecord
from tests.conftest import ALL_ROLE_DIRECTORY, REQUESTER, drive_to_completion


def _store() -> SqlPrecedentStore:
    engine = make_engine("sqlite:///:memory:")
    from app.adapters.persistence.db import init_db

    init_db(engine)
    return SqlPrecedentStore(make_session_factory(engine))


def _record(thread_id: str, subject: str, tags: list[str], at: str) -> PrecedentRecord:
    return PrecedentRecord(
        thread_id=thread_id,
        subject=subject,
        tags=tags,
        raw_request=f"request {thread_id}",
        verdict_type="approve",
        plan_kind="feasible",
        rationale="because",
        status="done",
        created_at=at,
    )


def test_round_trip_ranked_by_tag_overlap_then_recency() -> None:
    store = _store()
    store.record(_record("t1", "launch", ["a"], "2026-06-01T00:00:00Z"))
    store.record(_record("t2", "launch", ["a", "b"], "2026-06-02T00:00:00Z"))
    store.record(_record("t3", "launch", [], "2026-06-03T00:00:00Z"))
    store.record(_record("t4", "sso-ga", ["a", "b"], "2026-06-04T00:00:00Z"))  # other subject

    found = store.find_similar("launch", ["a", "b"], top_k=2)
    assert [r.thread_id for r in found] == ["t2", "t1"]  # overlap 2 > 1; subject filtered


def test_record_is_idempotent_per_thread() -> None:
    store = _store()
    store.record(_record("t1", "launch", ["a"], "2026-06-01T00:00:00Z"))
    store.record(_record("t1", "launch", ["a", "changed"], "2026-06-09T00:00:00Z"))
    found = store.find_similar("launch", ["a"], top_k=5)
    assert len(found) == 1 and found[0].tags == ["a"]  # first ruling stands


def test_render_precedents_is_bounded_and_safe() -> None:
    class _Exploding(MemoryPort):
        def record(self, record: PrecedentRecord) -> None: ...

        def find_similar(
            self, subject: str, tags: list[str], *, top_k: int = 3
        ) -> list[PrecedentRecord]:
            raise RuntimeError("memory down")

    assert render_precedents(None, "launch", []) == ""
    assert render_precedents(_Exploding(), "launch", []) == ""

    store = _store()
    store.record(
        _record("t1-very-long-thread-id", "launch", ["a"], "2026-06-01T00:00:00Z")
    )
    text = render_precedents(store, "launch", ["a"])
    assert "Past rulings" in text
    assert all(len(line) <= 200 for line in text.splitlines()[1:])


def test_completed_trial_is_recorded_as_precedent(tmp_path) -> None:  # type: ignore[no-untyped-def]
    db_url = f"sqlite:///{tmp_path.as_posix()}/court.db"
    service = build_court_service(
        Settings(
            force_all_mock=True,
            db_url=db_url,
            dry_run_default=True,
            approver_directory=ALL_ROLE_DIRECTORY,
        )
    )
    summary = service.submit_change(
        "slip the launch from 2026-06-10 to 2026-06-17", requester=REQUESTER
    )
    drive_to_completion(service, summary)

    # The container wires the precedent store into the same database the trial ran against.
    engine = make_engine(db_url)
    store = SqlPrecedentStore(make_session_factory(engine))
    found = store.find_similar("launch", ["schedule.milestone_move"], top_k=1)
    assert [r.thread_id for r in found] == [summary.thread_id]
    assert found[0].verdict_type == "approve"


def test_audit_node_records_precedent_with_fake_memory() -> None:
    from app.agent.nodes.audit import AuditNode
    from tests.test_audit_node import _MemAudit, _state

    class _CapturingMemory(MemoryPort):
        def __init__(self) -> None:
            self.records: list[PrecedentRecord] = []

        def record(self, record: PrecedentRecord) -> None:
            self.records.append(record)

        def find_similar(
            self, subject: str, tags: list[str], *, top_k: int = 3
        ) -> list[PrecedentRecord]:
            return self.records[:top_k]

    memory = _CapturingMemory()
    node = AuditNode(
        _MemAudit(), memory=memory, clock=lambda: "2026-06-04T00:00:00Z", id_factory=lambda: "a1"
    )
    node(_state())

    assert len(memory.records) == 1
    record = memory.records[0]
    assert record.thread_id == "t1"
    assert record.plan_kind  # extracted from the trial's options
    assert record.created_at == "2026-06-04T00:00:00Z"


def test_memory_failure_never_blocks_the_audit() -> None:
    from app.agent.nodes.audit import AuditNode
    from tests.test_audit_node import _MemAudit, _state

    class _Exploding(MemoryPort):
        def record(self, record: PrecedentRecord) -> None:
            raise RuntimeError("memory down")

        def find_similar(
            self, subject: str, tags: list[str], *, top_k: int = 3
        ) -> list[PrecedentRecord]:
            return []

    repo = _MemAudit()
    node = AuditNode(
        repo, memory=_Exploding(), clock=lambda: "2026-06-04T00:00:00Z", id_factory=lambda: "a1"
    )
    update = node(_state())

    assert update["audit_id"] == "a1"
    assert repo.get("a1") is not None  # the audit record landed despite the memory failure
