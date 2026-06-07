"""Signed deep links for the read-only run page.

A run-page URL carries an HMAC token scoped to one ``thread_id``: only someone handed the link
(via the Change Court card) can open that run, and a token for one run proves nothing about
another. The token is static per thread — the page is read-only inspection, so possession grants
nothing beyond seeing the trial it points at. Pure stdlib so both the card builder (generation)
and the REST router (verification) can import it without crossing façades.
"""

from __future__ import annotations

import base64
import hashlib
import hmac

# 18 bytes of MAC -> 24 url-safe chars: unforgeable in practice, short enough for a chat link.
_TOKEN_BYTES = 18


def sign_thread(thread_id: str, secret: str) -> str:
    """The url-safe token authorizing read access to one thread's run page."""
    mac = hmac.new(secret.encode(), thread_id.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac[:_TOKEN_BYTES]).rstrip(b"=").decode()


def verify_thread(thread_id: str, token: str, secret: str) -> bool:
    """Constant-time check of a presented token; an empty secret or token never verifies."""
    if not secret or not token:
        return False
    return hmac.compare_digest(sign_thread(thread_id, secret), token)


def run_page_url(base_url: str, thread_id: str, secret: str) -> str:
    """The absolute, signed run-page URL (local dev origin when no public base is set)."""
    origin = base_url.rstrip("/") or "http://localhost:8000"
    return f"{origin}/runs/{thread_id}?t={sign_thread(thread_id, secret)}"
