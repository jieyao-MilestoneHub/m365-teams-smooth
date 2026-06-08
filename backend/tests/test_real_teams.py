"""Real Teams adapter over recorded HTTP: downstream writes emit a real Graph activity notification,
reads stay seeded, and the non-idempotent write is never retried."""

from __future__ import annotations

import json

import httpx
import respx

from app.adapters.integrations.graph import GraphClient
from app.adapters.integrations.real_teams import RealTeamsAdapter
from app.adapters.integrations.retry import RetryClass
from app.domain import CapabilityRef, ExecutionStep, RunMode, StepStatus
from app.ports.integration import ReadQuery

_TOKEN_URL = "https://login.microsoftonline.com/t1/oauth2/v2.0/token"
_GRAPH = "https://graph.microsoft.com/v1.0"
_RECIPIENT = "approver@contoso.com"
_NOTIFY = f"{_GRAPH}/users/{_RECIPIENT}/teamwork/sendActivityNotification"


def _token_route() -> None:
    respx.post(_TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
    )


def _teams() -> RealTeamsAdapter:
    return RealTeamsAdapter(
        GraphClient("t1", "cid", "secret"),
        recipient_upn=_RECIPIENT,
        link_url="https://teams.microsoft.com/l/chat/0/0?users=28:bot",
    )


def _write_step(name: str, **params: object) -> ExecutionStep:
    return ExecutionStep(
        step_id="s1",
        capability=CapabilityRef(system="teams", name=name),
        params=params,
    )


@respx.mock
def test_live_post_message_sends_activity_notification() -> None:
    _token_route()
    notify = respx.post(_NOTIFY).mock(return_value=httpx.Response(202))
    step = _write_step("teams.post_message", channel="project-x", message="Weekly report ready")
    result = _teams().execute(step, RunMode.LIVE)
    assert result.status is StepStatus.OK
    assert notify.called
    assert result.after is not None and result.after["notified"] == _RECIPIENT
    sent = json.loads(notify.calls.last.request.content)
    assert sent["activityType"] == "systemDefault"
    assert "Weekly report" in sent["templateParameters"][0]["value"]


@respx.mock
def test_live_update_announcement_sends_activity_notification() -> None:
    _token_route()
    notify = respx.post(_NOTIFY).mock(return_value=httpx.Response(202))
    step = _write_step(
        "teams.update_announcement", channel="launch", message="Rehearsal moved to 2026-06-17"
    )
    result = _teams().execute(step, RunMode.LIVE)
    assert result.status is StepStatus.OK
    assert notify.called


@respx.mock
def test_dry_run_sends_no_notification() -> None:
    notify = respx.post(_NOTIFY).mock(return_value=httpx.Response(202))
    step = _write_step("teams.post_message", channel="project-x", message="x")
    result = _teams().execute(step, RunMode.DRY_RUN)
    assert result.status is StepStatus.DRY_RUN
    assert result.predicted is not None
    assert not notify.called
    assert not respx.calls  # a predicted notification touches Graph not at all


@respx.mock
def test_reads_return_seeded_evidence_without_graph() -> None:
    announcement = _teams().read(
        ReadQuery(capability="teams.read_announcement", params={"channel": "launch"})
    ).data
    assert "2026-06-10" in str(announcement["message"])
    notes = _teams().read(
        ReadQuery(capability="teams.read_meeting_notes", params={"channel": "standup"})
    ).data
    assert isinstance(notes["notes"], list) and len(notes["notes"]) == 4
    assert not respx.calls  # reads are served from the seeded source, never from Graph


@respx.mock
def test_graph_error_is_contained_as_failed() -> None:
    _token_route()
    respx.post(_NOTIFY).mock(return_value=httpx.Response(400))  # e.g. TeamsActivity.Send missing
    step = _write_step("teams.post_message", channel="project-x", message="x")
    result = _teams().execute(step, RunMode.LIVE)  # must not raise
    assert result.status is StepStatus.FAILED
    assert result.error is not None


def test_update_announcement_is_not_retried() -> None:
    # Despite the ".update_" name, an activity notification is not idempotent — guard the override.
    step = _write_step("teams.update_announcement", channel="launch", message="x")
    assert _teams()._retry_class_for(step) is RetryClass.NEVER_LANDED
