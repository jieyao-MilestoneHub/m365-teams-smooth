"""Verifications must survive the full chain: verify node → state → get_trial → result card."""

from __future__ import annotations

import json

from app.config import Settings
from app.container import build_court_service
from app.domain import RunMode, VerdictType
from app.mcp.cards import build_verdict_result_card
from app.services.court_service import CourtService


def _live_service() -> CourtService:
    return build_court_service(
        Settings(force_all_mock=True, db_url="sqlite:///:memory:", dry_run_default=False)
    )


def test_live_trial_verifications_reach_get_trial_and_card() -> None:
    service = _live_service()
    summary = service.submit_change(
        "slip the launch from 2026-06-10 to 2026-06-17", run_mode=RunMode.LIVE
    )
    cast = service.cast_verdict(summary.thread_id, VerdictType.APPROVE)
    assert cast.status == "done"

    trial = service.get_trial(summary.thread_id)
    assert trial is not None
    # The verify node ran on the live results and its output is visible through the service.
    assert trial.verifications, "live run must carry verifications through get_trial"
    assert all(v.checked is not None for v in trial.verifications)

    # The audit record carries the same verifications (the single stored copy).
    assert cast.audit_id is not None
    audit = service.get_audit(cast.audit_id)
    assert audit is not None
    assert [v.step_id for v in audit.trial.verifications] == [
        v.step_id for v in trial.verifications
    ]

    # A mismatch (if any) renders on the result card; a clean run renders without crashing.
    card = build_verdict_result_card(trial, status=cast.status, audit_id=cast.audit_id)
    json.dumps(card)  # serializable


def test_dry_run_trial_has_no_verifications() -> None:
    service = build_court_service(
        Settings(force_all_mock=True, db_url="sqlite:///:memory:", dry_run_default=True)
    )
    summary = service.submit_change("slip the launch from 2026-06-10 to 2026-06-17")
    service.cast_verdict(summary.thread_id, VerdictType.APPROVE)
    trial = service.get_trial(summary.thread_id)
    assert trial is not None
    assert trial.verifications == []
