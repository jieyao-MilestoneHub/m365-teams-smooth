"""The Change Court card renders the trial data and wires verdict buttons to cast_verdict."""

from __future__ import annotations

import json

from app.config import Settings
from app.container import build_court_service
from app.domain import VerdictType
from app.mcp.cards import build_change_court_card, build_verdict_result_card
from app.services.court_service import CourtService


def _service() -> CourtService:
    return build_court_service(
        Settings(force_all_mock=True, db_url="sqlite:///:memory:", dry_run_default=True)
    )


def _texts(card: dict[str, object]) -> str:
    return json.dumps(card)


def test_card_shows_safe_alternative_and_verdict_buttons() -> None:
    service = _service()
    summary = service.submit_change("promise Customer A that SSO is GA by 2026-06-17")
    trial = service.get_trial(summary.thread_id)
    assert trial is not None

    card = build_change_court_card(summary.thread_id, trial)
    assert card["type"] == "AdaptiveCard"
    blob = _texts(card)
    assert "Risk: HIGH" in blob
    assert "Unsafe as requested" in blob
    assert "Safe alternative" in blob

    actions = card["actions"]
    assert isinstance(actions, list)
    # one button per verdict option, each posting to cast_verdict with the selected plan
    verdicts = {a["data"]["verdict_type"] for a in actions}
    assert "accept_alternative" in verdicts
    assert all(a["data"]["tool"] == "cast_verdict" for a in actions)
    assert all(a["data"]["selected_plan"] == "safe_alternative" for a in actions)


def test_verdict_result_card_lists_steps() -> None:
    service = _service()
    summary = service.submit_change("slip the launch from 2026-06-10 to 2026-06-17")
    cast = service.cast_verdict(summary.thread_id, VerdictType.APPROVE)
    trial = service.get_trial(summary.thread_id)
    assert trial is not None

    card = build_verdict_result_card(trial, status=cast.status, audit_id=cast.audit_id)
    blob = _texts(card)
    assert "Verdict recorded" in blob
    assert "predicted" in blob  # dry-run steps are labelled predicted
