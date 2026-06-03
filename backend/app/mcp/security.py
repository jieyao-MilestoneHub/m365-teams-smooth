"""OAuth 2.0 for the MCP server: a bearer-token verifier with a local dev issuer.

The MCP server is a *resource server* — it validates access tokens, it does not issue them.
Locally (no tenant) a symmetric dev issuer mints and validates HS256 tokens so the OAuth-protected
flow is demonstrable end to end. Pointed at Entra ID (``OAUTH_*`` settings) the same seam validates
real tokens via JWKS — a follow-up that swaps the verifier without touching tools or services.
"""

from __future__ import annotations

import time

import jwt
from jwt import PyJWKClient
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from pydantic import AnyHttpUrl

from app.config import Settings

DEV_SECRET = "dev-only-not-a-secret-please-change-me"  # noqa: S105 — local dev issuer only
DEV_ISSUER = "https://change-court.local/dev"
DEV_AUDIENCE = "ai-change-court"
DEFAULT_SCOPES = ["court.use"]


def mint_dev_token(
    subject: str = "dev-user",
    scopes: list[str] | None = None,
    *,
    secret: str = DEV_SECRET,
    issuer: str = DEV_ISSUER,
    audience: str = DEV_AUDIENCE,
    ttl_seconds: int = 3600,
) -> str:
    """Mint a local HS256 access token for development and tests."""
    now = int(time.time())
    payload = {
        "sub": subject,
        "iss": issuer,
        "aud": audience,
        "iat": now,
        "exp": now + ttl_seconds,
        "scopes": scopes or DEFAULT_SCOPES,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def _access_token(token: str, claims: dict[str, object]) -> AccessToken:
    """Map validated JWT claims to an MCP AccessToken (shared by both verifiers)."""
    subject = str(claims.get("sub", ""))
    scopes = claims.get("scopes", [])
    return AccessToken(
        token=token,
        client_id=subject,
        scopes=list(scopes) if isinstance(scopes, list) else [],
        expires_at=claims.get("exp"),  # type: ignore[arg-type]
        subject=subject,
        claims=claims,
    )


class DevTokenVerifier(TokenVerifier):
    """Validates HS256 bearer tokens against the local dev issuer."""

    def __init__(
        self,
        *,
        secret: str = DEV_SECRET,
        issuer: str = DEV_ISSUER,
        audience: str = DEV_AUDIENCE,
    ) -> None:
        self._secret = secret
        self._issuer = issuer
        self._audience = audience

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            claims = jwt.decode(
                token,
                self._secret,
                algorithms=["HS256"],
                audience=self._audience,
                issuer=self._issuer,
            )
        except jwt.PyJWTError:
            return None
        return _access_token(token, claims)


class JwksTokenVerifier(TokenVerifier):
    """Validates RS256 bearer tokens issued by a tenant (e.g. Entra ID) via its JWKS endpoint."""

    def __init__(
        self,
        *,
        jwks_url: str,
        issuer: str,
        audience: str,
        jwk_client: PyJWKClient | None = None,
    ) -> None:
        self._issuer = issuer
        self._audience = audience
        self._jwks = jwk_client or PyJWKClient(jwks_url)

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            signing_key = self._jwks.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self._audience,
                issuer=self._issuer,
            )
        except jwt.PyJWTError:  # covers PyJWKClientError (a PyJWTError subclass) + decode failures
            return None
        return _access_token(token, claims)


def build_token_verifier(settings: Settings) -> TokenVerifier:
    """Build the token verifier for the environment.

    With a tenant issuer + JWKS configured (``OAUTH_ISSUER`` + ``OAUTH_JWKS_URL``) it validates real
    RS256 tokens via JWKS; otherwise it falls back to the local HS256 dev issuer.
    """
    if settings.oauth_issuer and settings.oauth_jwks_url:
        return JwksTokenVerifier(
            jwks_url=settings.oauth_jwks_url,
            issuer=settings.oauth_issuer,
            audience=settings.oauth_audience or DEV_AUDIENCE,
        )
    return DevTokenVerifier()


def build_auth_settings(settings: Settings) -> AuthSettings:
    """Resource-server auth settings (issuer, public resource URL, required scopes).

    Issuer and resource URL default to the local dev values; both follow configuration once
    ``OAUTH_ISSUER`` / ``PUBLIC_BASE_URL`` point at a real tenant and public host.
    """
    return AuthSettings(
        issuer_url=AnyHttpUrl(settings.oauth_issuer or DEV_ISSUER),
        resource_server_url=AnyHttpUrl(settings.mcp_resource_url()),
        required_scopes=DEFAULT_SCOPES,
    )
