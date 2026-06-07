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

    blob = _texts(
        build_verdict_result_card(trial, status=cast.execution_status, audit_id=cast.audit_id)
    )
    assert "Safe alternative executed" in blob
    assert "Refused the request as posed" in blob


def test_verdict_result_card_lists_steps_and_predicted() -> None:
    service = _service()
    summary = service.submit_change("slip the launch from 2026-06-10 to 2026-06-17")
    cast = service.cast_verdict(summary.thread_id, VerdictType.APPROVE)
    trial = service.get_trial(summary.thread_id)
    assert trial is not None

    blob = _texts(
        build_verdict_result_card(trial, status=cast.execution_status, audit_id=cast.audit_id)
    )
    assert "Verdict recorded" in blob
    assert "predicted" in blob  # dry-run steps are labelled predicted


def _trial(service: CourtService, raw: str):  # type: ignore[no-untyped-def]
    summary = service.submit_change(raw)
    trial = service.get_trial(summary.thread_id)
    assert trial is not None
    return summary.thread_id, trial


def test_requester_review_card_offers_send_and_give_up() -> None:
    thread_id, trial = _trial(_service(), "slip the launch from 2026-06-10 to 2026-06-17")
    card = build_change_court_card(thread_id, trial, status="awaiting_requester_review")

    actions = card["actions"]
    assert isinstance(actions, list)
    tools = [a["data"]["tool"] for a in actions]
    assert tools == ["send_for_approval", "withdraw_change"]
    # The mandatory note travels with the Send action via the card's input field.
    body = card["body"]
    assert isinstance(body, list)
    inputs = [b for b in body if isinstance(b, dict) and b.get("type") == "Input.Text"]
    assert inputs and inputs[0]["id"] == "note" and inputs[0]["isRequired"] is True


def test_approval_card_offers_decide_and_shows_requester_note() -> None:
    thread_id, trial = _trial(_service(), "slip the launch from 2026-06-10 to 2026-06-17")
    card = build_change_court_card(
        thread_id, trial, status="awaiting_approval", requester_note="please review by Friday"
    )

    blob = _texts(card)
    assert "Requester's note: please review by Friday" in blob
    actions = card["actions"]
    assert isinstance(actions, list)
    assert [a["data"]["tool"] for a in actions] == ["decide", "decide"]
    assert [a["data"]["approve"] for a in actions] == [True, False]
    # The note input exists for the reject reason but does not block Approve.
    body = card["body"]
    assert isinstance(body, list)
    inputs = [b for b in body if isinstance(b, dict) and b.get("type") == "Input.Text"]
    assert inputs and "isRequired" not in inputs[0]


def test_legacy_statuses_keep_cast_verdict_actions() -> None:
    thread_id, trial = _trial(_service(), "slip the launch from 2026-06-10 to 2026-06-17")
    for status in ("", "awaiting_verdict"):
        card = build_change_court_card(thread_id, trial, status=status)
        actions = card["actions"]
        assert isinstance(actions, list) and actions
        assert all(a["data"]["tool"] == "cast_verdict" for a in actions)


def test_actions_are_universal_execute_with_matching_verb() -> None:
    """Every phase emits Action.Execute whose verb mirrors data.tool, so the bot's invoke
    handler and legacy Action.Submit value routing resolve to the same service gate."""
    thread_id, trial = _trial(_service(), "slip the launch from 2026-06-10 to 2026-06-17")
    for status in ("awaiting_requester_review", "awaiting_approval", "awaiting_verdict"):
        card = build_change_court_card(thread_id, trial, status=status)
        actions = card["actions"]
        assert isinstance(actions, list) and actions
        for action in actions:
            assert action["type"] == "Action.Execute"
            assert action["verb"] == action["data"]["tool"]
            assert action["data"]["thread_id"] == thread_id


def _open_urls(card: dict[str, object]) -> list[dict[str, object]]:
    actions = card.get("actions")
    if not isinstance(actions, list):
        return []
    return [a for a in actions if isinstance(a, dict) and a.get("type") == "Action.OpenUrl"]


def test_run_link_adds_open_url_button_and_fallback_link() -> None:
    thread_id, trial = _trial(_service(), "slip the launch from 2026-06-10 to 2026-06-17")
    url = f"https://court.example.com/runs/{thread_id}?t=tok"
    card = build_change_court_card(
        thread_id, trial, status="awaiting_approval", run_link=lambda _tid: url
    )

    buttons = _open_urls(card)
    assert len(buttons) == 1
    assert buttons[0]["title"] == "View pipeline run"
    assert buttons[0]["url"] == url
    assert f"[Pipeline run log]({url})" in _texts(card)  # webview-safe fallback
    # The decision buttons stay first and unchanged.
    actions = card["actions"]
    assert isinstance(actions, list)
    assert [a["data"]["tool"] for a in actions if "data" in a] == ["decide", "decide"]


def test_no_run_link_renders_no_open_url() -> None:
    thread_id, trial = _trial(_service(), "slip the launch from 2026-06-10 to 2026-06-17")
    assert _open_urls(build_change_court_card(thread_id, trial)) == []
    # A generator returning None (RUN_LINK_SECRET unset) is equally a no-op.
    card = build_change_court_card(thread_id, trial, run_link=lambda _tid: None)
    assert _open_urls(card) == []


def test_result_card_carries_run_link_when_thread_known() -> None:
    service = _service()
    summary = service.submit_change("slip the launch from 2026-06-10 to 2026-06-17")
    cast = service.cast_verdict(summary.thread_id, VerdictType.APPROVE)
    trial = service.get_trial(summary.thread_id)
    assert trial is not None

    url = f"https://court.example.com/runs/{summary.thread_id}?t=tok"
    card = build_verdict_result_card(
        trial,
        status=cast.execution_status,
        audit_id=cast.audit_id,
        thread_id=summary.thread_id,
        run_link=lambda _tid: url,
    )
    assert _open_urls(card) == [
        {"type": "Action.OpenUrl", "title": "View pipeline run", "url": url}
    ]
    # Without a thread_id the result card cannot mint a link and must not guess one.
    bare = build_verdict_result_card(
        trial, status=cast.execution_status, audit_id=cast.audit_id, run_link=lambda _tid: url
    )
    assert _open_urls(bare) == []


def test_stage_strip_traces_the_pipeline_by_status() -> None:
    thread_id, trial = _trial(_service(), "slip the launch from 2026-06-10 to 2026-06-17")

    waiting = _texts(build_change_court_card(thread_id, trial, status="awaiting_approval"))
    assert "⏸ verdict" in waiting
    assert "✓ policy" in waiting
    assert "○ execute" in waiting

    done = _texts(build_verdict_result_card(trial, status="done", audit_id=None))
    assert "✓ audit" in done and "⏸" not in done

    blocked = _texts(build_change_court_card(thread_id, trial, status="blocked"))
    assert "⛔ intake" in blocked  # the hallucination guard is visible at a glance

    # An unknown/empty status renders no strip rather than a wrong one.
    assert "○ execute" not in _texts(build_change_court_card(thread_id, trial, status=""))
