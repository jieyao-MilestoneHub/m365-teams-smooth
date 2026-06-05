"""The /api/messages endpoint accepts Bot Framework activities in anonymous (local) mode."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.bot.court_bot import CourtBot
from app.bot.endpoint import build_bot_adapter, build_bot_router
from app.config import Settings
from app.container import build_court_service


def _client() -> TestClient:
    settings = Settings(
        force_all_mock=True, db_url="sqlite:///:memory:", dry_run_default=True
    )  # bot_app_id empty -> anonymous auth, as in the local Playground
    service = build_court_service(settings)
    app = FastAPI()
    app.include_router(build_bot_router(CourtBot(service), build_bot_adapter(settings)))
    # The reply connector is unreachable in tests; surface its failure as a 500, not a re-raise.
    return TestClient(app, raise_server_exceptions=False)


def _activity(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "type": "message",
        "id": "act-1",
        "text": "slip the launch from 2026-06-10 to 2026-06-17",
        "from": {"id": "user-1", "name": "requester@example.com"},
        "recipient": {"id": "bot"},
        "conversation": {"id": "conv-1"},
        "channelId": "emulator",
        "serviceUrl": "https://example.test",
    }
    base.update(overrides)
    return base


def test_message_activity_is_accepted() -> None:
    client = _client()
    response = client.post("/api/messages", json=_activity())
    # The reply card travels over the (unreachable) connector; the endpoint itself accepts the
    # turn. Anonymous mode must not reject the request for lack of an Authorization header.
    assert response.status_code in (200, 201, 500)
    assert response.status_code != 401


def test_invoke_activity_returns_card_in_response_body() -> None:
    client = _client()
    invoke = _activity(
        type="invoke",
        name="adaptiveCard/action",
        value={
            "action": {
                "type": "Action.Execute",
                "verb": "open_trial",
                "data": {"tool": "open_trial", "thread_id": "unknown-thread"},
            }
        },
    )
    response = client.post("/api/messages", json=invoke)
    # Invoke responses come back on the HTTP body — this is the in-place card refresh path.
    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "application/vnd.microsoft.card.adaptive"
    assert body["value"]["type"] == "AdaptiveCard"


def test_activity_without_a_type_is_rejected() -> None:
    client = _client()
    response = client.post("/api/messages", json={"text": "hi"})
    assert response.status_code == 400
