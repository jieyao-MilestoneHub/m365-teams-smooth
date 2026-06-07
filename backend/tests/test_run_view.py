"""The run view: node/step events, approval timeline, and incremental polling semantics."""

from __future__ import annotations

import pytest

from app.config import Settings
from app.container import build_court_service
from app.domain import ChangeStatus, Principal, VerdictType
from app.domain.errors import NotFoundError
from app.domain.run_events import RunEventKind
from app.services.court_service import CourtService


def _service(**overrides: object) -> CourtService:
    return build_court_service(
        Settings(
            force_all_mock=True,
            db_url="sqlite:///:memory:",
            dry_run_default=True,
            run_link_secret="test-secret",
            **overrides,  # type: ignore[arg-type]
        )
    )


def test_run_view_covers_the_full_pipeline() -> None:
    service = _service()
    summary = service.submit_change("slip the launch from 2026-06-10 to 2026-06-17")
    service.cast_verdict(summary.thread_id, VerdictType.APPROVE)

    view = service.get_run_view(summary.thread_id)

    finished = [e.name for e in view.events if e.kind is RunEventKind.NODE_FINISHED]
    for node in ("intake", "impact", "options", "policy", "execute", "verify", "audit"):
        assert node in finished, f"missing node_finished for {node}"
    steps = [e for e in view.events if e.kind is RunEventKind.STEP_FINISHED]
    assert steps, "execute must emit per-step events"
    assert all(e.payload.get("system") for e in steps)
    assert view.summary.status == ChangeStatus.DONE.value
    assert view.audit_id, "a concluded run links its audit record"
    assert view.run_mode == "dry_run"
    assert view.last_seq == max(e.seq for e in view.events)


def test_run_view_is_readable_at_the_verdict_gate() -> None:
    service = _service()
    summary = service.submit_change("slip the launch from 2026-06-10 to 2026-06-17")

    view = service.get_run_view(summary.thread_id)

    finished = [e.name for e in view.events if e.kind is RunEventKind.NODE_FINISHED]
    assert "policy" in finished
    assert "execute" not in finished  # suspended at the verdict interrupt
    assert view.summary.status == ChangeStatus.AWAITING_VERDICT.value
    assert view.audit_id is None


def test_run_view_polls_incrementally() -> None:
    service = _service()
    summary = service.submit_change("slip the launch from 2026-06-10 to 2026-06-17")

    first = service.get_run_view(summary.thread_id)
    assert first.events and first.last_seq > 0

    nothing_new = service.get_run_view(summary.thread_id, after_seq=first.last_seq)
    assert nothing_new.events == []
    assert nothing_new.last_seq == first.last_seq  # poller's cursor never regresses

    service.cast_verdict(summary.thread_id, VerdictType.APPROVE)
    tail = service.get_run_view(summary.thread_id, after_seq=first.last_seq)
    assert tail.events
    assert all(e.seq > first.last_seq for e in tail.events)


def test_run_view_folds_in_the_approval_timeline() -> None:
    requester = Principal(oid="oid-req", upn="req@example.com", display_name="Rae Quester")
    approver = Principal(oid="oid-app", upn="appr@example.com", display_name="Ann Prover")
    service = _service(approver_directory="eng_lead:oid-app,comms:oid-app")

    summary = service.submit_change(
        "slip the launch from 2026-06-10 to 2026-06-17", requester=requester
    )
    service.send_for_approval(summary.thread_id, actor=requester, note="please review")
    service.decide(summary.thread_id, actor=approver, approve=True, note="lgtm")

    view = service.get_run_view(summary.thread_id)
    decisions = [(a.decision, a.actor) for a in view.approvals]
    assert ("send", "Rae Quester") in decisions
    assert ("approve", "Ann Prover") in decisions
    assert all(a.at for a in view.approvals)


def test_unknown_thread_raises_not_found() -> None:
    service = _service()
    with pytest.raises(NotFoundError):
        service.get_run_view("never-ran")
