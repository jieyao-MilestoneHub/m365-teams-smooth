"""The JWKS verifier validates tenant RS256 tokens; the factory selects it when configured."""

from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Any, cast

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt import PyJWKClient

from app.config import Settings
from app.mcp.security import (
    DevTokenVerifier,
    JwksTokenVerifier,
    build_token_verifier,
)

_ISS = "https://login.microsoftonline.com/tenant-id/v2.0"
_AUD = "api://change-court"


def _keypair() -> tuple[bytes, Any]:
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    return pem, private.public_key()


def _token(private_pem: bytes, *, iss: str = _ISS, aud: str = _AUD) -> str:
    now = int(time.time())
    return jwt.encode(
        {"sub": "alice", "iss": iss, "aud": aud, "iat": now, "exp": now + 3600,
         "scopes": ["court.use"]},
        private_pem,
        algorithm="RS256",
    )


def _verifier(public_key: Any) -> JwksTokenVerifier:
    # Inject a stub resolver so no JWKS network call happens.
    stub = SimpleNamespace(
        get_signing_key_from_jwt=lambda _token: SimpleNamespace(key=public_key)
    )
    return JwksTokenVerifier(
        jwks_url="https://example/jwks",
        issuer=_ISS,
        audience=_AUD,
        jwk_client=cast(PyJWKClient, stub),
    )


async def test_valid_tenant_token_is_accepted() -> None:
    pem, public_key = _keypair()
    access = await _verifier(public_key).verify_token(_token(pem))
    assert access is not None
    assert access.client_id == "alice"
    assert "court.use" in access.scopes


async def test_wrong_audience_is_rejected() -> None:
    pem, public_key = _keypair()
    assert await _verifier(public_key).verify_token(_token(pem, aud="api://other")) is None


async def test_token_signed_by_a_different_key_is_rejected() -> None:
    pem, _ = _keypair()
    _, other_public_key = _keypair()
    assert await _verifier(other_public_key).verify_token(_token(pem)) is None


def test_factory_selects_jwks_when_issuer_and_jwks_set() -> None:
    settings = Settings(
        oauth_issuer=_ISS, oauth_jwks_url="https://example/jwks", oauth_audience=_AUD
    )
    assert isinstance(build_token_verifier(settings), JwksTokenVerifier)


def test_factory_defaults_to_dev_issuer() -> None:
    assert isinstance(build_token_verifier(Settings()), DevTokenVerifier)
