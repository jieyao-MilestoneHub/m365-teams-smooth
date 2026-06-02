"""Tests for the REST health endpoint."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app import __version__
from app.main import create_app


def test_health_returns_healthy() -> None:
    client = TestClient(create_app())
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body == {"status": "healthy", "version": __version__}
