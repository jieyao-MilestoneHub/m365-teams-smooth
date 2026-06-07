"""The mock Teams adapter surfaces a stale announcement and updates it / opens escalations."""

from __future__ import annotations

from app.adapters.integrations.mock_teams import MockTeamsAdapter
from app.domain import CapabilityRef, ExecutionStep, RunMode, StepStatus
from app.ports.integration import ReadQuery


def test_seeded_announcement_references_original_date() -> None:
    adapter = MockTeamsAdapter()
    data = adapter.read(
        ReadQuery(capability="teams.read_announcement", params={"channel": "launch"})
    ).data
    assert "2026-06-10" in str(data["message"])


def test_update_announcement_live_and_rollback_snapshot() -> None:
    adapter = MockTeamsAdapter()
    step = ExecutionStep(
        step_id="s1",
        capability=CapabilityRef(system="teams", name="teams.update_announcement"),
        params={"channel": "launch", "message": "Launch moved to 2026-06-17."},
    )
    result = adapter.execute(step, RunMode.LIVE)
    assert result.status is StepStatus.OK
    assert result.before == {"channel": "launch", "message": "Launch is scheduled for 2026-06-10."}
    data = adapter.read(
        ReadQuery(capability="teams.read_announcement", params={"channel": "launch"})
    ).data
    assert "2026-06-17" in str(data["message"])


def test_seeded_meeting_notes_carry_spoken_followups() -> None:
    adapter = MockTeamsAdapter()
    data = adapter.read(
        ReadQuery(capability="teams.read_meeting_notes", params={"channel": "standup"})
    ).data
    notes = data["notes"]
    assert isinstance(notes, list) and len(notes) == 4
    assert {n["author"] for n in notes} == {"Alex", "Jamie", "PM", "Sam"}
    assert any("2026-06-12" in n["text"] for n in notes)  # follow-ups carry their dates


def test_unknown_meeting_channel_returns_no_notes() -> None:
    adapter = MockTeamsAdapter()
    data = adapter.read(
        ReadQuery(capability="teams.read_meeting_notes", params={"channel": "nope"})
    ).data
    assert data["notes"] == []


def test_escalation_thread_created_live() -> None:
    adapter = MockTeamsAdapter()
    step = ExecutionStep(
        step_id="s1",
        capability=CapabilityRef(system="teams", name="teams.create_escalation_thread"),
        params={"channel": "deals", "title": "SSO GA risk"},
    )
    result = adapter.execute(step, RunMode.LIVE)
    assert result.status is StepStatus.OK
    assert result.after is not None and "thread" in result.after


def test_post_message_live_and_dry_run() -> None:
    adapter = MockTeamsAdapter()
    step = ExecutionStep(
        step_id="s1",
        capability=CapabilityRef(system="teams", name="teams.post_message"),
        params={"channel": "project-x", "message": "Weekly report: 4 issues closed."},
    )
    dry = adapter.execute(step, RunMode.DRY_RUN)
    assert dry.status is StepStatus.DRY_RUN
    assert dry.predicted is not None and "post" in dry.predicted.summary
    live = adapter.execute(step, RunMode.LIVE)
    assert live.status is StepStatus.OK
    assert live.after is not None and "post" in live.after
    assert live.before == {"posts": 0}  # snapshot taken before the post landed
