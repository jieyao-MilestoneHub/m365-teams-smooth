"""Managed input shield — Azure AI Content Safety Prompt Shields.

Screens the user prompt and any retrieved documents for prompt-injection / jailbreak attempts via
the ``text:shieldPrompt`` endpoint. Keyless auth (``DefaultAzureCredential``), matching the other
Azure adapters. This is a *configured real* shield: if it cannot screen (transport, auth, or
timeout failure) it **raises** rather than returning an unflagged verdict — never assume unscreened
input is safe. (The offline heuristic shield, used when no endpoint is configured, never raises.)
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

import httpx
from azure.identity import DefaultAzureCredential, get_bearer_token_provider

from app.domain import SOURCE_AZURE_PROMPT_SHIELDS, ShieldVerdict
from app.domain.errors import GuardrailError
from app.ports.guardrail import GuardrailPort

logger = logging.getLogger(__name__)

_SCOPE = "https://cognitiveservices.azure.com/.default"
_API_VERSION = "2024-09-01"


class AzurePromptShieldsGuardrail(GuardrailPort):
    """Calls Azure AI Content Safety Prompt Shields to classify untrusted input."""

    def __init__(
        self,
        *,
        endpoint: str,
        api_version: str = _API_VERSION,
        timeout: float = 10.0,
        token_provider: Any | None = None,
    ) -> None:
        self._url = f"{endpoint.rstrip('/')}/contentsafety/text:shieldPrompt"
        self._api_version = api_version
        self._timeout = timeout
        self._token = token_provider or get_bearer_token_provider(
            DefaultAzureCredential(), _SCOPE
        )

    def screen_input(self, *, user_text: str, documents: Sequence[str] = ()) -> ShieldVerdict:
        try:
            response = httpx.post(
                self._url,
                params={"api-version": self._api_version},
                headers={"Authorization": f"Bearer {self._token()}"},
                json={"userPrompt": user_text, "documents": list(documents)},
                timeout=self._timeout,
            )
            response.raise_for_status()
            data = response.json()
        except Exception as exc:  # noqa: BLE001 — a configured shield that cannot screen fails loud
            logger.warning("guardrail.shield_unavailable", extra={"error": str(exc)})
            raise GuardrailError(f"prompt shield unavailable: {exc}") from exc

        return _verdict_from(data)


def _verdict_from(data: dict[str, Any]) -> ShieldVerdict:
    """Map the Prompt Shields response to a verdict (user-prompt + per-document attack flags)."""
    categories: list[str] = []
    prompt_analysis = data.get("userPromptAnalysis")
    if isinstance(prompt_analysis, dict) and prompt_analysis.get("attackDetected"):
        categories.append("user_prompt_attack")
    docs_analysis = data.get("documentsAnalysis")
    if isinstance(docs_analysis, list) and any(
        isinstance(d, dict) and d.get("attackDetected") for d in docs_analysis
    ):
        categories.append("document_attack")
    return ShieldVerdict(
        flagged=bool(categories), categories=categories, source=SOURCE_AZURE_PROMPT_SHIELDS
    )
