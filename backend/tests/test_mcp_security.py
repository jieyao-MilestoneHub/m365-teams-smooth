"""The token verifiers accept valid tokens and reject tampered/expired/wrong-audience ones."""

from __future__ import annotations

import time

import pytest
from mcp.server.auth.middleware.auth_context import auth_context_var
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser

from app.config import Settings
from app.container import build_court_service
from app.mcp.security import (
    DEV_AUDIENCE,
    DEV_ISSUER,
    DEV_SECRET,
    DevTokenVerifier,
    JwksTokenVerifier,
    build_auth_settings,
    build_transport_security,
    current_principal,
    mint_dev_token,
    principal_from_claims,
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


def _rs256_jwks_verifier() -> tuple[JwksTokenVerifier, object]:
    """A JwksTokenVerifier with an in-test RSA keypair stubbed in as the JWKS client."""
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    class _StubSigningKey:
        def __init__(self, public_key: object) -> None:
            self.key = public_key

    class _StubJwkClient:
        def get_signing_key_from_jwt(self, _token: str) -> _StubSigningKey:
            return _StubSigningKey(key.public_key())

    verifier = JwksTokenVerifier(
        jwks_url="https://unused.example/jwks",
        issuer="https://login.microsoftonline.com/tenant-id/v2.0",
        audience="api://client-guid",
        jwk_client=_StubJwkClient(),  # type: ignore[arg-type]
    )
    return verifier, key


def _mint_rs256(key: object, *, aud: str, **extra: object) -> str:
    import jwt as pyjwt

    now = int(time.time())
    payload: dict[str, object] = {
        "sub": "user-oid",
        "iss": "https://login.microsoftonline.com/tenant-id/v2.0",
        "aud": aud,
        "iat": now,
        "exp": now + 600,
        **extra,
    }
    return pyjwt.encode(payload, key, algorithm="RS256")  # type: ignore[arg-type]


async def test_entra_v2_token_with_bare_guid_audience_and_scp_is_accepted() -> None:
    # Entra v2 access tokens carry the bare client id as `aud` and scopes in `scp`.
    verifier, key = _rs256_jwks_verifier()
    token = _mint_rs256(key, aud="client-guid", scp="court.use")
    access = await verifier.verify_token(token)
    assert access is not None
    assert "court.use" in access.scopes


async def test_v1_style_api_uri_audience_is_accepted() -> None:
    verifier, key = _rs256_jwks_verifier()
    token = _mint_rs256(key, aud="api://client-guid", scp="court.use")
    assert await verifier.verify_token(token) is not None


async def test_app_only_roles_map_to_scopes() -> None:
    verifier, key = _rs256_jwks_verifier()
    token = _mint_rs256(key, aud="client-guid", roles=["court.use"])
    access = await verifier.verify_token(token)
    assert access is not None
    assert "court.use" in access.scopes


async def test_jwks_rejection_logs_the_reason(caplog: pytest.LogCaptureFixture) -> None:
    # Rejections must be observable: a wrong-audience token logs mcp.token_rejected.
    verifier, key = _rs256_jwks_verifier()
    token = _mint_rs256(key, aud="someone-else", scp="court.use")
    with caplog.at_level("WARNING"):
        assert await verifier.verify_token(token) is None
    assert any(r.message == "mcp.token_rejected" for r in caplog.records)


def test_transport_security_allows_the_public_host() -> None:
    # Behind an ingress the Host header is the public FQDN; the DNS-rebinding guard must
    # allow it (and keep local dev hosts working) instead of answering 421.
    ts = build_transport_security(
        Settings(public_base_url="https://change-court.example.com")
    )
    assert "change-court.example.com" in ts.allowed_hosts
    assert "https://change-court.example.com" in ts.allowed_origins
    assert "localhost:*" in ts.allowed_hosts


def test_transport_security_defaults_to_local_hosts() -> None:
    ts = build_transport_security(Settings())
    assert "localhost:*" in ts.allowed_hosts
    assert ts.enable_dns_rebinding_protection


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


def test_principal_from_entra_claims() -> None:
    principal = principal_from_claims(
        {"oid": "11111111-aaaa", "preferred_username": "alice@contoso.com", "name": "Alice"}
    )
    assert principal.oid == "11111111-aaaa"
    assert principal.upn == "alice@contoso.com"
    assert principal.display_name == "Alice"


def test_principal_falls_back_across_claim_spellings() -> None:
    # No oid/preferred_username: sub fills oid, upn fills upn — any standard issuer works.
    principal = principal_from_claims({"sub": "user-42", "upn": "bob@contoso.com"})
    assert principal.oid == "user-42"
    assert principal.upn == "bob@contoso.com"


async def test_principal_from_dev_token_claims() -> None:
    access = await DevTokenVerifier().verify_token(mint_dev_token("alice"))
    assert access is not None and access.claims is not None
    assert principal_from_claims(access.claims).key() == "alice"


def test_current_principal_is_none_without_request_context() -> None:
    assert current_principal() is None


async def test_current_principal_reads_the_bound_auth_context() -> None:
    # Bind the contextvar exactly as AuthContextMiddleware does for an authenticated request.
    access = await DevTokenVerifier().verify_token(mint_dev_token("alice"))
    assert access is not None
    token = auth_context_var.set(AuthenticatedUser(access))
    try:
        principal = current_principal()
    finally:
        auth_context_var.reset(token)
    assert principal is not None and principal.key() == "alice"


def test_resource_url_defaults_to_localhost() -> None:
    assert Settings().mcp_resource_url() == "http://localhost:8000/mcp"


def test_resource_url_follows_public_base_url() -> None:
    settings = Settings(public_base_url="https://change-court.example.com/")
    assert settings.mcp_resource_url() == "https://change-court.example.com/mcp"


def test_auth_settings_advertise_public_resource_url() -> None:
    settings = Settings(public_base_url="https://change-court.example.com")
    auth = build_auth_settings(settings)
    assert str(auth.resource_server_url).rstrip("/") == "https://change-court.example.com/mcp"
