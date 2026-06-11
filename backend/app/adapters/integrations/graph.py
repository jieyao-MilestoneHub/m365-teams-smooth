"""Microsoft Graph client: app-only (client-credentials) token + GET/POST helpers.

Shared by the read-only real Graph adapters (Outlook calendar, SharePoint folders) and the Teams
activity notifier. App-only auth keeps the backend free of a user-delegated flow: with
admin-consented *application* permissions it reads a specific user's calendar and a specific
site's drive. ``post`` signals activity-feed notifications and ``post_json`` performs the contained
calendar/draft writes; the base adapter still predicts (never mutates) under DRY_RUN.

Errors surface as raised exceptions; ``BaseIntegrationAdapter`` maps them to ``IntegrationError`` at
the boundary, so a Graph failure is contained like any other adapter error.
"""

from __future__ import annotations

import time

import httpx

_LOGIN = "https://login.microsoftonline.com"
_GRAPH = "https://graph.microsoft.com/v1.0"
_SCOPE = "https://graph.microsoft.com/.default"


class GraphClient:
    """App-only Microsoft Graph client with a cached client-credentials token."""

    def __init__(
        self,
        tenant_id: str,
        client_id: str,
        client_secret: str,
        *,
        client: httpx.Client | None = None,
        login_url: str = _LOGIN,
        graph_url: str = _GRAPH,
    ) -> None:
        self._token_url = f"{login_url}/{tenant_id}/oauth2/v2.0/token"
        self._graph_url = graph_url.rstrip("/")
        self._client_id = client_id
        self._client_secret = client_secret
        self._http = client or httpx.Client(timeout=15.0)
        self._cached_token: str | None = None
        self._expiry = 0.0

    def _bearer(self) -> str:
        if self._cached_token and time.time() < self._expiry:
            return self._cached_token
        resp = self._http.post(
            self._token_url,
            data={
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "grant_type": "client_credentials",
                "scope": _SCOPE,
            },
        )
        resp.raise_for_status()
        body = resp.json()
        self._cached_token = str(body["access_token"])
        # Refresh a minute early to avoid using a token that expires mid-request.
        self._expiry = time.time() + int(body.get("expires_in", 3600)) - 60
        return self._cached_token

    def get(self, path: str, **params: object) -> dict[str, object]:
        """GET an absolute-or-relative Graph path and return the parsed JSON object."""
        query = {k: str(v) for k, v in params.items()}
        resp = self._http.get(
            f"{self._graph_url}{path}",
            headers={"Authorization": f"Bearer {self._bearer()}"},
            params=query or None,
        )
        resp.raise_for_status()
        return dict(resp.json())

    def get_content(self, path: str) -> bytes:
        """GET a Graph path and return the raw body bytes (for ``…:/content`` downloads).

        Content downloads answer with a 302 to a pre-signed storage URL, so this request —
        unlike :meth:`get` — follows redirects.
        """
        resp = self._http.get(
            f"{self._graph_url}{path}",
            headers={"Authorization": f"Bearer {self._bearer()}"},
            follow_redirects=True,
        )
        resp.raise_for_status()
        return resp.content

    def post(self, path: str, payload: dict[str, object]) -> None:
        """POST a JSON payload to a Graph path; raises on any non-success status."""
        resp = self._http.post(
            f"{self._graph_url}{path}",
            headers={"Authorization": f"Bearer {self._bearer()}"},
            json=payload,
        )
        resp.raise_for_status()

    def post_json(self, path: str, payload: dict[str, object]) -> dict[str, object]:
        """POST a JSON payload and return the parsed response body (raises on non-success).

        Like :meth:`post`, but for the contained writes that need the created resource back (its id
        and ``webLink``); an empty body (e.g. a ``202 Accepted``) maps to ``{}``.
        """
        resp = self._http.post(
            f"{self._graph_url}{path}",
            headers={"Authorization": f"Bearer {self._bearer()}"},
            json=payload,
        )
        resp.raise_for_status()
        return dict(resp.json()) if resp.content else {}
