"""ApprovalLedger contract: the in-memory fake and the SQL adapter behave identically."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from app.adapters.persistence.db import init_db, make_engine, make_session_factory
from app.adapters.persistence.repositories import SqlApprovalLedger
from app.domain import ApprovalDecision, ApprovalEvent, Principal
from app.ports.repository import ApprovalLedger
from tests.conftest import InMemoryApprovalLedger

ACTOR = Principal(oid="a-1", upn="a@x")


def _sql_ledger() -> SqlApprovalLedger:
    engine = make_engine("sqlite:///:memory:")
    init_db(engine)
    return SqlApprovalLedger(make_session_factory(engine))


def _event(thread_id: str, decision: ApprovalDecision, note: str, at: str) -> ApprovalEvent:
    return ApprovalEvent(
        event_id=f"{thread_id}-{decision.value}-{at}",
        thread_id=thread_id,
        actor=ACTOR,
        decision=decision,
        note=note,
        at=at,
    )


@pytest.fixture(params=[InMemoryApprovalLedger, _sql_ledger], ids=["memory", "sql"])
def ledger(request: pytest.FixtureRequest) -> ApprovalLedger:
    factory: Callable[[], ApprovalLedger] = request.param
    return factory()


def test_events_round_trip_in_order(ledger: ApprovalLedger) -> None:
    ledger.append(_event("t1", ApprovalDecision.SEND, "please", "2026-06-01T00:00:00+00:00"))
    ledger.append(_event("t1", ApprovalDecision.APPROVE, "", "2026-06-02T00:00:00+00:00"))
    events = ledger.list_for_thread("t1")
    assert [e.decision for e in events] == [ApprovalDecision.SEND, ApprovalDecision.APPROVE]
    assert ledger.list_for_thread("other") == []
    assert ledger.thread_ids() == ["t1"]


def test_first_note_filters_by_decision(ledger: ApprovalLedger) -> None:
    ledger.append(_event("t1", ApprovalDecision.SEND, "the send note", "2026-06-01T00:00:00+00:00"))
    ledger.append(_event("t1", ApprovalDecision.REJECT, "the veto", "2026-06-02T00:00:00+00:00"))
    assert ledger.first_note("t1", ApprovalDecision.SEND) == "the send note"
    assert ledger.first_note("t1", ApprovalDecision.REJECT) == "the veto"
    assert ledger.first_note("t1", ApprovalDecision.WITHDRAW) == ""
    assert ledger.first_note("missing", ApprovalDecision.SEND) == ""


def test_pending_lifecycle_is_idempotent_and_ordered(ledger: ApprovalLedger) -> None:
    ledger.mark_pending("t2", "2026-06-02T00:00:00+00:00")
    ledger.mark_pending("t1", "2026-06-01T00:00:00+00:00")
    ledger.mark_pending("t1", "2026-06-09T00:00:00+00:00")  # re-mark keeps the first entry
    assert ledger.pending_thread_ids() == ["t1", "t2"]  # ordered by created_at

    ledger.clear_pending("t1")
    ledger.clear_pending("t1")  # clearing twice is a no-op
    ledger.clear_pending("never-marked")
    assert ledger.pending_thread_ids() == ["t2"]
