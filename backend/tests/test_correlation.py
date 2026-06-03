"""Correlation contextvars, the formatter merge, and the HTTP request-ID middleware."""

from __future__ import annotations

import json
import logging

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.observability.context import bind, current_context, reset
from app.observability.logging import JsonFormatter
from app.observability.middleware import REQUEST_ID_HEADER


def _record() -> logging.LogRecord:
    return logging.makeLogRecord({"name": "app.test", "levelname": "INFO", "msg": "hi"})


def test_bind_sets_and_reset_restores_context() -> None:
    assert current_context() == {}

    tokens = bind(request_id="r1", thread_id="t1")
    assert current_context() == {"request_id": "r1", "thread_id": "t1"}

    reset(tokens)
    assert current_context() == {}


def test_bind_rejects_unknown_field() -> None:
    with pytest.raises(KeyError):
        bind(nope="x")


def test_formatter_merges_current_context() -> None:
    tokens = bind(request_id="r9", change_id="c9")
    try:
        payload = json.loads(JsonFormatter().format(_record()))
    finally:
        reset(tokens)

    assert payload["request_id"] == "r9"
    assert payload["change_id"] == "c9"


def test_middleware_generates_request_id_when_absent() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.headers[REQUEST_ID_HEADER]


def test_middleware_preserves_inbound_request_id() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/api/health", headers={REQUEST_ID_HEADER: "inbound-123"})

    assert response.headers[REQUEST_ID_HEADER] == "inbound-123"


def test_middleware_resets_context_after_request() -> None:
    with TestClient(create_app()) as client:
        client.get("/api/health", headers={REQUEST_ID_HEADER: "inbound-123"})

    # The request scope's binding must not leak into the surrounding context.
    assert current_context() == {}
