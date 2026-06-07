"""The run-page router: signed-link auth (401), feature-off (404), and the poll payload."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_court_service
from app.config import Settings
from app.container import build_court_service
from app.main import create_app
from app.services.court_service import CourtService


def _service(secret: str = "test-secret") -> CourtService:
    return build_court_service(
        Settings(
            force_all_mock=True,
            db_url="sqlite:///:memory:",
            dry_run_default=True,
            run_link_secret=secret,
        )
    )


@pytest.fixture
def client_and_service() -> Iterator[tuple[TestClient, CourtService]]:
    service = _service()
    app = create_app()
    app.dependency_overrides[get_court_service] = lambda: service
    try:
        yield TestClient(app), service
    finally:
        app.dependency_overrides.clear()


def _submitted(service: CourtService) -> str:
    return service.submit_change("slip the launch from 2026-06-10 to 2026-06-17").thread_id


def test_missing_token_is_unauthorized(client_and_service: tuple[TestClient, CourtService]) -> None:
    client, service = client_and_service
    thread_id = _submitted(service)
    assert client.get(f"/runs/{thread_id}").status_code == 401
    assert client.get(f"/api/runs/{thread_id}/events").status_code == 401


def test_bad_token_is_unauthorized(client_and_service: tuple[TestClient, CourtService]) -> None:
    client, service = client_and_service
    thread_id = _submitted(service)
    assert client.get(f"/runs/{thread_id}?t=forged").status_code == 401


def test_token_for_another_thread_is_unauthorized(
    client_and_service: tuple[TestClient, CourtService],
) -> None:
    client, service = client_and_service
    thread_id = _submitted(service)
    other = service.run_token("some-other-thread")
    assert client.get(f"/runs/{thread_id}?t={other}").status_code == 401


def test_valid_token_serves_page_and_events(
    client_and_service: tuple[TestClient, CourtService],
) -> None:
    client, service = client_and_service
    thread_id = _submitted(service)
    token = service.run_token(thread_id)

    page = client.get(f"/runs/{thread_id}?t={token}")
    assert page.status_code == 200
    assert page.headers["content-type"].startswith("text/html")
    assert page.headers["referrer-policy"] == "no-referrer"
    assert page.headers["x-robots-tag"] == "noindex"

    poll = client.get(f"/api/runs/{thread_id}/events?t={token}")
    assert poll.status_code == 200
    body = poll.json()
    assert body["summary"]["thread_id"] == thread_id
    assert body["last_seq"] >= 1
    assert any(e["kind"] == "node_started" and e["name"] == "intake" for e in body["events"])


def test_unknown_thread_with_valid_token_is_not_found(
    client_and_service: tuple[TestClient, CourtService],
) -> None:
    client, service = client_and_service
    token = service.run_token("never-ran")
    assert client.get(f"/api/runs/never-ran/events?t={token}").status_code == 404


def test_secret_unset_disables_the_surface() -> None:
    service = _service(secret="")
    app = create_app()
    app.dependency_overrides[get_court_service] = lambda: service
    try:
        client = TestClient(app)
        thread_id = _submitted(service)
        # Fail closed as 404 — with no secret nothing can verify, so the page does not exist.
        assert client.get(f"/runs/{thread_id}?t=whatever").status_code == 404
        assert client.get(f"/api/runs/{thread_id}/events").status_code == 404
        assert service.run_link(thread_id) is None
    finally:
        app.dependency_overrides.clear()
