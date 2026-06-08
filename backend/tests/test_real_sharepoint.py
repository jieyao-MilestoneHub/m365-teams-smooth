"""Live SharePoint grant over recorded HTTP: a real least-privilege, time-boxed Graph invite, with
the dry-run / error-containment / boundary-validation guarantees the base class promises."""

from __future__ import annotations

import json

import httpx
import respx

from app.adapters.integrations.graph import GraphClient
from app.adapters.integrations.real_sharepoint import RealSharePointAdapter
from app.domain import CapabilityRef, ExecutionStep, RunMode, StepStatus

_TOKEN_URL = "https://login.microsoftonline.com/t1/oauth2/v2.0/token"
_GRAPH = "https://graph.microsoft.com/v1.0"
_DRIVES = f"{_GRAPH}/sites/site1/drives"
_ITEM = f"{_GRAPH}/sites/site1/drives/d1/root:/LaunchAssets:"
_INVITE = f"{_GRAPH}/sites/site1/drives/d1/items/item1/invite"


def _token_route() -> None:
    respx.post(_TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
    )


def _drives_route() -> None:
    respx.get(_DRIVES).mock(
        return_value=httpx.Response(200, json={"value": [{"id": "d1", "name": "ProjectX"}]})
    )


def _item_route() -> None:
    respx.get(_ITEM).mock(return_value=httpx.Response(200, json={"id": "item1"}))


def _sharepoint() -> RealSharePointAdapter:
    return RealSharePointAdapter(GraphClient("t1", "cid", "secret"), "site1")


def _grant_step(**overrides: object) -> ExecutionStep:
    params: dict[str, object] = {
        "path": "/ProjectX/LaunchAssets",
        "principal": "vendor@example.com",
        "role": "read",
        "expiry": "2026-06-30",
    }
    params.update(overrides)
    return ExecutionStep(
        step_id="s1",
        capability=CapabilityRef(system="sharepoint", name="sharepoint.grant_folder_permission"),
        params=params,
    )


@respx.mock
def test_live_grant_calls_invite() -> None:
    _token_route()
    _drives_route()
    _item_route()
    invite = respx.post(_INVITE).mock(
        return_value=httpx.Response(200, json={"value": [{"id": "perm1", "roles": ["read"]}]})
    )
    result = _sharepoint().execute(_grant_step(), RunMode.LIVE)
    assert result.status is StepStatus.OK
    assert invite.called
    assert result.after is not None
    grant = result.after["grant"]
    assert isinstance(grant, dict)
    assert grant["permission_id"] == "perm1"
    assert grant["drive_id"] == "d1" and grant["item_id"] == "item1"


@respx.mock
def test_dry_run_makes_no_write_call() -> None:
    invite = respx.post(_INVITE).mock(return_value=httpx.Response(200, json={"value": []}))
    result = _sharepoint().execute(_grant_step(), RunMode.DRY_RUN)
    assert result.status is StepStatus.DRY_RUN
    assert result.predicted is not None
    assert not invite.called
    assert not respx.calls  # a predicted grant touches Graph not at all


@respx.mock
def test_role_maps_read_and_write_to_graph_roles() -> None:
    for role in ("read", "write"):
        respx.calls.reset()
        _token_route()
        _drives_route()
        _item_route()
        invite = respx.post(_INVITE).mock(
            return_value=httpx.Response(200, json={"value": [{"id": "perm1"}]})
        )
        _sharepoint().execute(_grant_step(role=role), RunMode.LIVE)
        sent = json.loads(invite.calls.last.request.content)
        assert sent["roles"] == [role]
        assert sent["sendInvitation"] is False and sent["requireSignIn"] is True


@respx.mock
def test_unsupported_role_is_contained_as_failed() -> None:
    invite = respx.post(_INVITE).mock(return_value=httpx.Response(200, json={"value": []}))
    result = _sharepoint().execute(_grant_step(role="owner"), RunMode.LIVE)
    assert result.status is StepStatus.FAILED
    assert result.error is not None and "unsupported role" in result.error
    assert not invite.called  # rejected before any Graph call


@respx.mock
def test_expiry_becomes_expiration_datetime() -> None:
    _token_route()
    _drives_route()
    _item_route()
    invite = respx.post(_INVITE).mock(
        return_value=httpx.Response(200, json={"value": [{"id": "perm1"}]})
    )
    _sharepoint().execute(_grant_step(), RunMode.LIVE)
    sent = json.loads(invite.calls.last.request.content)
    assert sent["expirationDateTime"] == "2026-06-30T00:00:00Z"


@respx.mock
def test_no_expiry_omits_expiration_datetime() -> None:
    _token_route()
    _drives_route()
    _item_route()
    invite = respx.post(_INVITE).mock(
        return_value=httpx.Response(200, json={"value": [{"id": "perm1"}]})
    )
    step = _grant_step()
    del step.params["expiry"]
    _sharepoint().execute(step, RunMode.LIVE)
    sent = json.loads(invite.calls.last.request.content)
    assert "expirationDateTime" not in sent


@respx.mock
def test_http_403_is_contained_as_failed() -> None:
    _token_route()
    _drives_route()
    _item_route()
    respx.post(_INVITE).mock(return_value=httpx.Response(403))  # Sites.ReadWrite.All not consented
    result = _sharepoint().execute(_grant_step(), RunMode.LIVE)  # must not raise
    assert result.status is StepStatus.FAILED
    assert result.error is not None


@respx.mock
def test_injected_path_traversal_is_rejected_before_any_call() -> None:
    drives = respx.get(_DRIVES).mock(return_value=httpx.Response(200, json={"value": []}))
    result = _sharepoint().execute(_grant_step(path="/ProjectX/../../etc"), RunMode.LIVE)
    assert result.status is StepStatus.FAILED
    assert result.error is not None and "invalid path" in result.error
    assert not drives.called  # rejected in safe_path before resolving anything


@respx.mock
def test_injected_principal_is_rejected_before_any_call() -> None:
    drives = respx.get(_DRIVES).mock(return_value=httpx.Response(200, json={"value": []}))
    result = _sharepoint().execute(_grant_step(principal="not an email"), RunMode.LIVE)
    assert result.status is StepStatus.FAILED
    assert result.error is not None and "invalid email" in result.error
    assert not drives.called


@respx.mock
def test_rollback_hint_names_delete_endpoint() -> None:
    _token_route()
    _drives_route()
    _item_route()
    respx.post(_INVITE).mock(
        return_value=httpx.Response(200, json={"value": [{"id": "perm1"}]})
    )
    result = _sharepoint().execute(_grant_step(), RunMode.LIVE)
    assert result.rollback is not None
    assert "DELETE" in result.rollback.instruction
    assert "permissions" in result.rollback.instruction
