"""The typed error mapping behaves identically across the REST and MCP surfaces."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from mcp import McpError

from app.api.errors import classify, error_body, mcp_code
from app.config import Settings
from app.domain.errors import (
    CapabilityNotFoundError,
    ChangeCourtError,
    IntegrationError,
    NotFoundError,
    UnsafeChangeError,
    VerdictConflictError,
)
from app.main import create_app
from app.mcp.tools import _translate_errors
from app.observability.middleware import REQUEST_ID_HEADER


def test_classify_maps_each_domain_error() -> None:
    assert classify(NotFoundError("x")) == (404, "not_found")
    assert classify(CapabilityNotFoundError("x")) == (422, "capability_not_found")
    assert classify(UnsafeChangeError("x")) == (409, "unsafe_change")
    assert classify(VerdictConflictError("x")) == (409, "verdict_conflict")
    assert classify(IntegrationError("x")) == (502, "integration_error")
    assert classify(ChangeCourtError("x")) == (500, "internal_error")


def test_classify_unknown_error_is_internal() -> None:
    assert classify(ValueError("boom")) == (500, "internal_error")


def test_error_body_shape() -> None:
    assert error_body("not_found", "missing", "rid-1") == {
        "error": "not_found",
        "detail": "missing",
        "request_id": "rid-1",
    }


def _client() -> TestClient:
    app = create_app(Settings(force_all_mock=True, db_url="sqlite:///:memory:"))

    @app.get("/raise-domain")
    def _raise_domain() -> None:
        raise NotFoundError("unknown trial: t1")

    @app.get("/raise-integration")
    def _raise_integration() -> None:
        raise IntegrationError("github: upstream unavailable")

    @app.get("/raise-unexpected")
    def _raise_unexpected() -> None:
        raise RuntimeError("a secret internal detail")

    return TestClient(app, raise_server_exceptions=False)


def test_rest_domain_error_maps_status_body_and_echoes_request_id() -> None:
    resp = _client().get("/raise-domain", headers={REQUEST_ID_HEADER: "rid-abc"})
    assert resp.status_code == 404
    assert resp.json() == {
        "error": "not_found",
        "detail": "unknown trial: t1",
        "request_id": "rid-abc",
    }
    # The body's request_id matches the id the middleware bound and echoed.
    assert resp.headers[REQUEST_ID_HEADER] == "rid-abc"


def test_rest_integration_error_is_502() -> None:
    resp = _client().get("/raise-integration")
    body = resp.json()
    assert resp.status_code == 502
    assert body["error"] == "integration_error"
    assert body["request_id"]  # a fresh id was generated


def test_rest_unexpected_error_is_500_with_generic_detail() -> None:
    resp = _client().get("/raise-unexpected")
    body = resp.json()
    assert resp.status_code == 500
    assert body["error"] == "internal_error"
    assert body["detail"] == "internal error"  # the real message is never leaked
    assert "secret" not in body["detail"]


def test_mcp_translate_errors_raises_structured_error() -> None:
    @_translate_errors
    def _tool() -> dict[str, object]:
        raise NotFoundError("unknown trial: t1")

    with pytest.raises(McpError) as excinfo:
        _tool()

    err = excinfo.value.error
    assert err.code == mcp_code("not_found")
    data = err.data
    assert isinstance(data, dict)
    assert data["error"] == "not_found"
    assert data["detail"] == "unknown trial: t1"
    assert data["request_id"]  # a request id is always present


def test_mcp_translate_errors_passes_through_success() -> None:
    @_translate_errors
    def _tool() -> dict[str, object]:
        return {"ok": True}

    assert _tool() == {"ok": True}
