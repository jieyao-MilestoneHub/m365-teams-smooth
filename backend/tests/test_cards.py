"""The Change Court card foregrounds the refusal, decisive evidence, and the safe alternative."""

from __future__ import annotations

import json

from app.config import Settings
from app.container import build_court_service
from app.domain import PlanKind, VerdictType
from app.mcp.cards import build_change_court_card, build_verdict_result_card
from app.services.court_service import CourtService


def _service() -> CourtService:
    return build_court_service(
        Settings(force_all_mock=True, db_url="sqlite:///:memory:", dry_run_default=True)
    )


def _texts(card: dict[str, object]) -> str:
    return json.dumps(card, ensure_ascii=False)


def test_unsafe_card_leads_with_refusal_and_decisive_evidence() -> None:
    service = _service()
    summary = service.submit_change("promise Customer A that SSO is GA by 2026-06-17")
    trial = service.get_trial(summary.thread_id)
    assert trial is not None

    card = build_change_court_card(summary.thread_id, trial)
    assert card["type"] == "AdaptiveCard"
    blob = _texts(card)
    assert "Risk: HIGH" in blob
    assert "REJECTED as requested" in blob  # the refusal is explicit
    assert "Decisive evidence" in blob
    # the decisive contradiction is surfaced, with its grounded citation
    assert "Security review on 2026-06-18 is after the promised 2026-06-17" in blob
    assert "GA Readiness Policy" in blob
    assert "Safe alternative" in blob

    actions = card["actions"]
    assert isinstance(actions, list)
    verdicts = {a["data"]["verdict_type"] for a in actions}
    assert "accept_alternative" in verdicts
    assert all(a["data"]["tool"] == "cast_verdict" for a in actions)
    assert all(a["data"]["selected_plan"] == "safe_alternative" for a in actions)


def test_feasible_card_has_no_decisive_block_but_shows_impact() -> None:
    service = _service()
    summary = service.submit_change("slip the launch from 2026-06-10 to 2026-06-17")
    trial = service.get_trial(summary.thread_id)
    assert trial is not None

    blob = _texts(build_change_court_card(summary.thread_id, trial))
    assert "REJECTED as requested" not in blob  # feasible, not refused
    assert "Decisive evidence" not in blob  # no high-severity evidence
    assert "Impact evidence" in blob


def test_verdict_result_card_for_accepted_alternative_reads_as_refusal() -> None:
    service = _service()
    summary = service.submit_change("promise Customer A that SSO is GA by 2026-06-17")
    cast = service.cast_verdict(
        summary.thread_id, VerdictType.ACCEPT_ALTERNATIVE, selected_plan=PlanKind.SAFE_ALTERNATIVE
    )
    trial = service.get_trial(summary.thread_id)
    assert trial is not None

    blob = _texts(build_verdict_result_card(trial, status=cast.status, audit_id=cast.audit_id))
    assert "Safe alternative executed" in blob
    assert "Refused the request as posed" in blob


def test_verdict_result_card_lists_steps_and_predicted() -> None:
    service = _service()
    summary = service.submit_change("slip the launch from 2026-06-10 to 2026-06-17")
    cast = service.cast_verdict(summary.thread_id, VerdictType.APPROVE)
    trial = service.get_trial(summary.thread_id)
    assert trial is not None

    blob = _texts(build_verdict_result_card(trial, status=cast.status, audit_id=cast.audit_id))
    assert "Verdict recorded" in blob
    assert "predicted" in blob  # dry-run steps are labelled predicted
