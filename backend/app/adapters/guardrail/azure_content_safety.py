"""Managed input shield — Azure AI Content Safety Prompt Shields.

Screens the user prompt and any retrieved documents for prompt-injection / jailbreak attempts via
the ``text:shieldPrompt`` endpoint. Keyless auth (``DefaultAzureCredential``), matching the other
Azure adapters. Screening degrades gracefully: any transport, auth, or timeout failure returns an
unflagged verdict marked unavailable, so a slow or down shield never fails the trial.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

import httpx
from azure.identity import DefaultAzureCredential, get_bearer_token_provider

from app.domain import SOURCE_AZURE_PROMPT_SHIELDS, SOURCE_UNAVAILABLE, ShieldVerdict
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
        except Exception as exc:  # noqa: BLE001 — screening is advisory; never fail the trial
            logger.warning("guardrail.shield_unavailable", extra={"error": str(exc)})
            return ShieldVerdict(source=SOURCE_UNAVAILABLE)

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
