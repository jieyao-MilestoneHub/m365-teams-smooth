"""Read-only real Graph adapters over recorded HTTP: token caching, reads, and dry-run safety."""

from __future__ import annotations

import httpx
import respx

from app.adapters.integrations.graph import GraphClient
from app.adapters.integrations.real_outlook import RealOutlookAdapter
from app.adapters.integrations.real_sharepoint import RealSharePointAdapter
from app.domain import CapabilityRef, ExecutionStep, RunMode, StepStatus
from app.ports.integration import ReadQuery

_TOKEN_URL = "https://login.microsoftonline.com/t1/oauth2/v2.0/token"
_GRAPH = "https://graph.microsoft.com/v1.0"


def _token_route() -> None:
    respx.post(_TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
    )


# --- GraphClient -----------------------------------------------------------------


@respx.mock
def test_graph_client_caches_token_across_calls() -> None:
    token = respx.post(_TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
    )
    events = respx.get(f"{_GRAPH}/users/u/events").mock(
        return_value=httpx.Response(200, json={"value": []})
    )
    client = GraphClient("t1", "cid", "secret")
    client.get("/users/u/events")
    client.get("/users/u/events")
    assert events.call_count == 2
    # The token is fetched once and reused (not re-requested per Graph call).
    assert token.call_count == 1


# --- Outlook (read-only) ---------------------------------------------------------


def _outlook() -> RealOutlookAdapter:
    return RealOutlookAdapter(GraphClient("t1", "cid", "secret"), "user@contoso.com")


@respx.mock
def test_read_security_review_returns_earliest_matching_date() -> None:
    _token_route()
    respx.get(f"{_GRAPH}/users/user@contoso.com/events").mock(
        return_value=httpx.Response(
            200,
            json={
                "value": [
                    {"subject": "Daily standup", "start": {"dateTime": "2026-06-15T09:00:00"}},
                    {
                        "subject": "SSO Security Review",
                        "start": {"dateTime": "2026-06-18T09:00:00.0"},
                    },
                    {
                        "subject": "SSO security review (backup)",
                        "start": {"dateTime": "2026-06-20T09:00:00"},
                    },
                ]
            },
        )
    )
    data = _outlook().read(
        ReadQuery(capability="outlook.read_security_review", params={"subject": "SSO"})
    ).data
    assert data["review_date"] == "2026-06-18"  # earliest of the two matching reviews


@respx.mock
def test_read_security_review_none_when_no_match() -> None:
    _token_route()
    respx.get(f"{_GRAPH}/users/user@contoso.com/events").mock(
        return_value=httpx.Response(200, json={"value": [{"subject": "Lunch", "start": {}}]})
    )
    data = _outlook().read(ReadQuery(capability="outlook.read_security_review")).data
    assert data["review_date"] is None


@respx.mock
def test_read_events_returns_normalized_list() -> None:
    _token_route()
    respx.get(f"{_GRAPH}/users/user@contoso.com/events").mock(
        return_value=httpx.Response(
            200,
            json={
                "value": [
                    {
                        "subject": "Launch dry-run",
                        "start": {"dateTime": "2026-06-17T09:00:00"},
                        "end": {"dateTime": "2026-06-17T10:00:00"},
                    }
                ]
            },
        )
    )
    data = _outlook().read(ReadQuery(capability="outlook.read_events")).data
    assert data["events"] == [
        {"title": "Launch dry-run", "start": "2026-06-17T09:00:00", "end": "2026-06-17T10:00:00"}
    ]


@respx.mock
def test_real_outlook_dry_run_predicts_no_write() -> None:
    step = ExecutionStep(
        step_id="s1",
        capability=CapabilityRef(system="outlook", name="outlook.create_event"),
        params={"title": "Review", "start": "2026-06-18"},
    )
    result = _outlook().execute(step, RunMode.DRY_RUN)
    assert result.status is StepStatus.DRY_RUN
    assert result.predicted is not None
    assert not respx.calls  # dry-run never calls Graph


# Live Outlook writes (create_event / draft_email) are covered in test_real_outlook.py.


# --- SharePoint (read-only) ------------------------------------------------------


def _sharepoint() -> RealSharePointAdapter:
    return RealSharePointAdapter(GraphClient("t1", "cid", "secret"), "site1")


def _drives_route() -> None:
    # The first path segment ("ProjectX") resolves to a document library (drive).
    respx.get(f"{_GRAPH}/sites/site1/drives").mock(
        return_value=httpx.Response(
            200,
            json={"value": [{"id": "d1", "name": "ProjectX"}, {"id": "d0", "name": "Documents"}]},
        )
    )


@respx.mock
def test_read_folder_flags_customer_data() -> None:
    _token_route()
    _drives_route()
    respx.get(f"{_GRAPH}/sites/site1/drives/d1/root/children").mock(
        return_value=httpx.Response(
            200,
            json={
                "value": [
                    {"name": "LaunchAssets", "folder": {}},
                    {"name": "CustomerData", "folder": {}},
                ]
            },
        )
    )
    data = _sharepoint().read(
        ReadQuery(capability="sharepoint.read_folder", params={"path": "/ProjectX"})
    ).data
    assert data["contains_customer_data"] is True
    items = data["items"]
    assert isinstance(items, list) and "CustomerData" in items


@respx.mock
def test_real_sharepoint_live_grant_predicts_instead_of_failing() -> None:
    step = ExecutionStep(
        step_id="s1",
        capability=CapabilityRef(system="sharepoint", name="sharepoint.grant_folder_permission"),
        params={"path": "/ProjectX", "principal": "vendor@x.com", "role": "read"},
    )
    # Read-only-real: the grant is predicted (not applied) and never reaches Graph.
    result = _sharepoint().execute(step, RunMode.LIVE)  # must not raise
    assert result.status is StepStatus.DRY_RUN
    assert result.predicted is not None
    assert result.error is None
    assert not respx.calls


@respx.mock
def test_read_folder_safe_subfolder_has_no_customer_data() -> None:
    _token_route()
    _drives_route()
    respx.get(f"{_GRAPH}/sites/site1/drives/d1/root:/LaunchAssets:/children").mock(
        return_value=httpx.Response(
            200, json={"value": [{"name": "brief.docx"}, {"name": "timeline.xlsx"}]}
        )
    )
    data = _sharepoint().read(
        ReadQuery(capability="sharepoint.read_folder", params={"path": "/ProjectX/LaunchAssets"})
    ).data
    assert data["contains_customer_data"] is False
