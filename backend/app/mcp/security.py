"""OAuth 2.0 for the MCP server: a bearer-token verifier with a local dev issuer.

The MCP server is a *resource server* — it validates access tokens, it does not issue them.
Locally (no tenant) a symmetric dev issuer mints and validates HS256 tokens so the OAuth-protected
flow is demonstrable end to end. Pointed at Entra ID (``OAUTH_*`` settings) the same seam validates
real tokens via JWKS — a follow-up that swaps the verifier without touching tools or services.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Mapping

import jwt
from jwt import PyJWKClient
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import AnyHttpUrl

from app.config import Settings
from app.domain.principal import Principal

DEV_SECRET = "dev-only-not-a-secret-please-change-me"  # noqa: S105 — local dev issuer only
DEV_ISSUER = "https://change-court.local/dev"
DEV_AUDIENCE = "ai-change-court"
DEFAULT_SCOPES = ["court.use"]

logger = logging.getLogger(__name__)


def _audience_candidates(audience: str) -> list[str]:
    """Both spellings of an Entra application audience.

    v1 access tokens carry the Application ID URI (``api://<client-id>``) while v2 tokens carry
    the bare client id — accept whichever the tenant mints for the same app.
    """
    candidates = [audience]
    if audience.startswith("api://"):
        candidates.append(audience.removeprefix("api://"))
    else:
        candidates.append(f"api://{audience}")
    return candidates


def _claim_scopes(claims: Mapping[str, object]) -> list[str]:
    """Normalize the scope claim across issuers.

    The dev issuer mints ``scopes`` (list); Entra delegated tokens carry ``scp`` (space-delimited
    string) and app-only tokens carry ``roles`` (list).
    """
    scopes = claims.get("scopes")
    if isinstance(scopes, list):
        return [str(s) for s in scopes]
    scp = claims.get("scp")
    if isinstance(scp, str) and scp:
        return scp.split()
    roles = claims.get("roles")
    if isinstance(roles, list):
        return [str(r) for r in roles]
    return []


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
    return AccessToken(
        token=token,
        client_id=subject,
        scopes=_claim_scopes(claims),
        expires_at=claims.get("exp"),  # type: ignore[arg-type]
        subject=subject,
        claims=claims,
    )


def principal_from_claims(claims: Mapping[str, object]) -> Principal:
    """Map validated token claims to a :class:`Principal`.

    Claim names follow standard OIDC with Entra ID spellings first, falling back across the common
    variants so tokens from any standards-compliant issuer (including the local dev issuer, which
    only sets ``sub``) yield a usable identity.
    """

    def first(*keys: str) -> str:
        for key in keys:
            value = claims.get(key)
            if isinstance(value, str) and value:
                return value
        return ""

    return Principal(
        oid=first("oid", "sub"),
        upn=first("preferred_username", "upn", "email"),
        display_name=first("name"),
    )


def current_principal() -> Principal | None:
    """The authenticated caller of the current MCP request, or ``None`` when unauthenticated.

    Reads the access token the auth middleware bound for this request; tools use ``None`` to select
    the legacy (identity-free) flow, so unauthenticated local runs keep working unchanged.
    """
    token = get_access_token()
    if token is None or not token.claims:
        return None
    principal = principal_from_claims(token.claims)
    return principal if principal.key() else None


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
        except jwt.PyJWTError as err:
            logger.warning("mcp.token_rejected", extra={"verifier": "dev", "reason": str(err)})
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
        self._audiences = _audience_candidates(audience)
        self._jwks = jwk_client or PyJWKClient(jwks_url)

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            signing_key = self._jwks.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self._audiences,
                issuer=self._issuer,
            )
        except jwt.PyJWTError as err:  # covers PyJWKClientError (a PyJWTError subclass) too
            logger.warning("mcp.token_rejected", extra={"verifier": "jwks", "reason": str(err)})
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


def build_transport_security(settings: Settings) -> TransportSecuritySettings:
    """Allow the public host through the SDK's DNS-rebinding guard.

    The streamable-HTTP transport rejects requests whose Host header is not allow-listed (421).
    Behind an ingress the Host is the public FQDN, so derive it from ``PUBLIC_BASE_URL``; local
    dev hosts stay allowed on any port.
    """
    from urllib.parse import urlparse

    allowed_hosts = ["localhost", "localhost:*", "127.0.0.1", "127.0.0.1:*"]
    allowed_origins = ["http://localhost:*", "http://127.0.0.1:*"]
    if settings.public_base_url:
        parsed = urlparse(settings.public_base_url)
        if parsed.netloc:
            allowed_hosts.extend([parsed.netloc, f"{parsed.netloc}:443"])
            allowed_origins.append(f"{parsed.scheme}://{parsed.netloc}")
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=allowed_hosts,
        allowed_origins=allowed_origins,
    )


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
