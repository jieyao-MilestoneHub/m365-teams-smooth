"""Live Outlook writes over recorded HTTP: real calendar events and unsent drafts, with the
dry-run / error-containment / boundary-validation guarantees the base class promises."""

from __future__ import annotations

import json

import httpx
import respx

from app.adapters.integrations.graph import GraphClient
from app.adapters.integrations.real_outlook import RealOutlookAdapter
from app.domain import CapabilityRef, ExecutionStep, RunMode, StepStatus

_TOKEN_URL = "https://login.microsoftonline.com/t1/oauth2/v2.0/token"
_GRAPH = "https://graph.microsoft.com/v1.0"
_UPN = "user@contoso.com"
_EVENTS = f"{_GRAPH}/users/{_UPN}/events"
_MESSAGES = f"{_GRAPH}/users/{_UPN}/messages"


def _token_route() -> None:
    respx.post(_TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
    )


def _outlook() -> RealOutlookAdapter:
    return RealOutlookAdapter(GraphClient("t1", "cid", "secret"), _UPN)


def _create_step(**params: object) -> ExecutionStep:
    base: dict[str, object] = {
        "title": "Launch rehearsal: moved to 2026-06-18",
        "start": "2026-06-18",
    }
    base.update(params)
    return ExecutionStep(
        step_id="s1",
        capability=CapabilityRef(system="outlook", name="outlook.create_event"),
        params=base,
    )


def _draft_step(**params: object) -> ExecutionStep:
    base: dict[str, object] = {
        "to": "customer@example.com",
        "subject": "SSO availability",
        "body": "Hi there",
    }
    base.update(params)
    return ExecutionStep(
        step_id="s1",
        capability=CapabilityRef(system="outlook", name="outlook.draft_email"),
        params=base,
    )


@respx.mock
def test_live_create_event_posts_to_calendar() -> None:
    _token_route()
    events = respx.post(_EVENTS).mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "evt-1",
                "subject": "Launch rehearsal: moved to 2026-06-18",
                "start": {"dateTime": "2026-06-18T09:00:00", "timeZone": "UTC"},
                "webLink": "https://outlook.office365.com/calendar/item/evt-1",
            },
        )
    )
    result = _outlook().execute(_create_step(), RunMode.LIVE)
    assert result.status is StepStatus.OK
    assert events.called
    assert result.after is not None
    created = result.after["created_event"]
    assert isinstance(created, dict) and created["id"] == "evt-1"
    # The created event's web link is surfaced so a reviewer can open it from the run page/card.
    assert result.resource_url == "https://outlook.office365.com/calendar/item/evt-1"
    # The plan carries a date only; the adapter sends a 09:00–10:00 UTC timed slot.
    sent = json.loads(events.calls.last.request.content)
    assert set(sent) == {"subject", "start", "end", "body"}
    assert sent["start"] == {"dateTime": "2026-06-18T09:00:00", "timeZone": "UTC"}
    assert sent["end"] == {"dateTime": "2026-06-18T10:00:00", "timeZone": "UTC"}


@respx.mock
def test_live_draft_email_creates_unsent_draft() -> None:
    _token_route()
    messages = respx.post(_MESSAGES).mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "msg-1",
                "subject": "SSO availability",
                "isDraft": True,
                "webLink": "https://outlook.office365.com/mail/draft/msg-1",
            },
        )
    )
    result = _outlook().execute(_draft_step(), RunMode.LIVE)
    assert result.status is StepStatus.OK
    assert messages.called
    assert result.after is not None
    draft = result.after["draft"]
    assert isinstance(draft, dict)
    assert draft["id"] == "msg-1"
    assert draft["sent"] is False  # created in Drafts, never sent
    sent = json.loads(messages.calls.last.request.content)
    assert sent["toRecipients"][0]["emailAddress"]["address"] == "customer@example.com"
    assert sent["body"]["contentType"] == "text"


@respx.mock
def test_dry_run_creates_no_event_and_no_draft() -> None:
    create = _outlook().execute(_create_step(), RunMode.DRY_RUN)
    draft = _outlook().execute(_draft_step(), RunMode.DRY_RUN)
    assert create.status is StepStatus.DRY_RUN and create.predicted is not None
    assert draft.status is StepStatus.DRY_RUN and draft.predicted is not None
    assert not respx.calls  # dry-run never calls Graph


@respx.mock
def test_http_error_on_create_is_contained_as_failed() -> None:
    _token_route()
    respx.post(_EVENTS).mock(return_value=httpx.Response(403))  # Calendars.ReadWrite not consented
    result = _outlook().execute(_create_step(), RunMode.LIVE)  # must not raise
    assert result.status is StepStatus.FAILED
    assert result.error is not None


@respx.mock
def test_http_error_on_draft_is_contained_as_failed() -> None:
    _token_route()
    respx.post(_MESSAGES).mock(return_value=httpx.Response(403))  # Mail.ReadWrite not consented
    result = _outlook().execute(_draft_step(), RunMode.LIVE)
    assert result.status is StepStatus.FAILED
    assert result.error is not None


@respx.mock
def test_injected_recipient_is_rejected_before_any_call() -> None:
    messages = respx.post(_MESSAGES).mock(return_value=httpx.Response(200, json={}))
    result = _outlook().execute(
        _draft_step(to="victim@evil.com\r\nBcc: leak@evil.com"), RunMode.LIVE
    )
    assert result.status is StepStatus.FAILED
    assert result.error is not None and "invalid email" in result.error
    assert not messages.called  # rejected before reaching Graph


@respx.mock
def test_injected_subject_crlf_is_rejected_before_any_call() -> None:
    messages = respx.post(_MESSAGES).mock(return_value=httpx.Response(200, json={}))
    result = _outlook().execute(_draft_step(subject="Hi\r\nX-Inject: 1"), RunMode.LIVE)
    assert result.status is StepStatus.FAILED
    assert result.error is not None and "control characters" in result.error
    assert not messages.called


@respx.mock
def test_malformed_start_date_is_rejected_before_any_call() -> None:
    events = respx.post(_EVENTS).mock(return_value=httpx.Response(200, json={}))
    result = _outlook().execute(_create_step(start="not-a-date"), RunMode.LIVE)
    assert result.status is StepStatus.FAILED
    assert result.error is not None and "invalid start date" in result.error
    assert not events.called
