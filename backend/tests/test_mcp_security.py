"""The dev token verifier accepts valid tokens and rejects tampered/expired/wrong-audience ones."""

from __future__ import annotations

from app.config import Settings
from app.container import build_court_service
from app.mcp.security import (
    DEV_AUDIENCE,
    DEV_ISSUER,
    DEV_SECRET,
    DevTokenVerifier,
    build_auth_settings,
    mint_dev_token,
)
from app.mcp.server import build_mcp_server


async def test_valid_dev_token_is_accepted() -> None:
    verifier = DevTokenVerifier()
    token = mint_dev_token("alice", ["court.use"])
    access = await verifier.verify_token(token)
    assert access is not None
    assert access.client_id == "alice"
    assert "court.use" in access.scopes


async def test_tampered_token_is_rejected() -> None:
    verifier = DevTokenVerifier()
    assert await verifier.verify_token(mint_dev_token() + "x") is None


async def test_expired_token_is_rejected() -> None:
    verifier = DevTokenVerifier()
    expired = mint_dev_token(ttl_seconds=-10)
    assert await verifier.verify_token(expired) is None


async def test_wrong_audience_is_rejected() -> None:
    verifier = DevTokenVerifier()
    other = mint_dev_token(secret=DEV_SECRET, issuer=DEV_ISSUER, audience="someone-else")
    assert await verifier.verify_token(other) is None


def test_server_builds_with_auth_enabled() -> None:
    # Auth-enabled server still builds + registers tools (transport enforces auth, not call_tool).
    service = build_court_service(
        Settings(force_all_mock=True, db_url="sqlite:///:memory:"), packs=[]
    )
    mcp = build_mcp_server(
        service,
        token_verifier=DevTokenVerifier(),
        auth_settings=build_auth_settings(Settings()),
    )
    assert mcp is not None


def test_dev_audience_constant() -> None:
    assert DEV_AUDIENCE  # sanity: a non-empty default audience exists
