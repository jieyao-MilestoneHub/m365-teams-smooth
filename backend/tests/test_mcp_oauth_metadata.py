"""The MCP 401 must advertise a protected-resource-metadata URL that is actually served.

Regression guard for the mounted-subpath discovery bug: the FastMCP SDK serves the RFC 9728
document only under its ``/mcp`` mount, but its ``WWW-Authenticate`` advertises the document at the
ROOT path. A client follows the advertised URL to discover the auth server and start sign-in; if
that URL 404s, no sign-in is ever triggered. ``create_full_app`` must serve the document at the
advertised root path.
"""

from __future__ import annotations

import re

from starlette.testclient import TestClient

from app.asgi import create_full_app
from app.config import Settings
from app.container import build_court_service


def _client() -> TestClient:
    service = build_court_service(Settings(force_all_mock=True, db_url="sqlite:///:memory:"))
    return TestClient(create_full_app(service))


def test_unauthenticated_mcp_advertises_a_reachable_metadata_url() -> None:
    with _client() as client:
        unauth = client.post("/mcp", json={})
        assert unauth.status_code == 401
        header = unauth.headers.get("www-authenticate", "")
        match = re.search(r'resource_metadata="([^"]+)"', header)
        assert match, f"no resource_metadata in WWW-Authenticate: {header!r}"

        # Follow the advertised URL as a spec-compliant client would (strip scheme+host).
        advertised_path = "/" + match.group(1).split("/", 3)[-1]
        resp = client.get(advertised_path)
        assert resp.status_code == 200, f"advertised metadata URL 404s: {advertised_path}"
        body = resp.json()
        assert body["resource"].endswith("/mcp")
        assert body["authorization_servers"]
        assert "court.use" in body["scopes_supported"]


def test_metadata_served_at_the_root_well_known_path() -> None:
    with _client() as client:
        resp = client.get("/.well-known/oauth-protected-resource/mcp")
        assert resp.status_code == 200
        body = resp.json()
        assert body["resource"].endswith("/mcp")
        assert body["bearer_methods_supported"] == ["header"]
