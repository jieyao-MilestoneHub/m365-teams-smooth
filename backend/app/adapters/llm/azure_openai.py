"""Real LLM provider: Azure OpenAI chat completions, behind the LLMProvider port.

``generate`` honors the port's structured-output intent natively: a ``json_schema`` on the request
becomes a strict ``response_format`` (the service guarantees schema-conforming JSON), and a
truncated or refused structured response raises ``LlmOutputError`` so callers fall back to their
deterministic baselines instead of parsing a broken payload. Auth is keyless
(``DefaultAzureCredential`` bearer token) unless an API key is given; an injected ``client`` is
accepted for tests (mirrors the Foundry IQ provider). Selected in the composition root only when an
endpoint + deployment are set; otherwise the offline FakeLLMProvider stays the default, so the
trials remain credential-free.
"""

from __future__ import annotations

import logging
from typing import Any

import openai
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from openai import AzureOpenAI

from app.domain.errors import LlmOutputError
from app.observability import metrics
from app.ports.llm import LLMProvider, LlmRequest, LlmResult

logger = logging.getLogger(__name__)

_SCOPE = "https://cognitiveservices.azure.com/.default"


def _error_class(exc: Exception) -> str:
    """Map an SDK failure to a stable taxonomy (most specific first — these types nest)."""
    if isinstance(exc, openai.RateLimitError):
        return "rate_limited"
    if isinstance(exc, openai.APITimeoutError):
        return "timeout"
    if isinstance(exc, openai.APIConnectionError):
        return "connection"
    if isinstance(exc, openai.APIStatusError):
        return "server" if exc.status_code >= 500 else "invalid_request"
    return "unknown"


class AzureOpenAILLMProvider(LLMProvider):
    """Generates text via an Azure OpenAI chat deployment."""

    def __init__(
        self,
        *,
        endpoint: str,
        deployment: str,
        api_version: str,
        api_key: str = "",
        timeout: float | None = None,
        max_tokens: int | None = None,
        max_retries: int = 2,
        client: Any | None = None,
    ) -> None:
        self._deployment = deployment
        self._max_tokens = max_tokens
        if client is not None:
            self._client: Any = client
        elif api_key:
            self._client = AzureOpenAI(
                azure_endpoint=endpoint,
                api_version=api_version,
                api_key=api_key,
                timeout=timeout,
                max_retries=max_retries,
            )
        else:
            token_provider = get_bearer_token_provider(DefaultAzureCredential(), _SCOPE)
            self._client = AzureOpenAI(
                azure_endpoint=endpoint,
                api_version=api_version,
                azure_ad_token_provider=token_provider,
                timeout=timeout,
                max_retries=max_retries,
            )

    def complete(self, prompt: str, *, system: str | None = None) -> str:
        return self.generate(LlmRequest(prompt=prompt, cacheable_prefix=system)).text

    def generate(self, request: LlmRequest) -> LlmResult:
        # The service caches on an exact, stable prompt prefix (engaged from ~1024 tokens), so the
        # cacheable text leads as its own system message and every volatile part comes after it.
        messages: list[dict[str, str]] = []
        if request.cacheable_prefix:
            messages.append({"role": "system", "content": request.cacheable_prefix})
        if request.system_suffix:
            messages.append({"role": "system", "content": request.system_suffix})
        messages.append({"role": "user", "content": request.prompt})
        extra: dict[str, Any] = {}
        if request.json_schema is not None:
            extra["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": request.schema_name,
                    "strict": True,
                    "schema": request.json_schema,
                },
            }
        try:
            response = self._client.chat.completions.create(
                model=self._deployment,
                messages=messages,
                temperature=0,
                max_tokens=request.max_tokens or self._max_tokens,
                **extra,
            )
        except Exception as exc:
            # The SDK has already spent its retry budget by the time this raises. Classify the
            # failure so throttling, timeouts, and bad requests are distinguishable in operations;
            # callers keep their deterministic fallbacks, so the error itself still propagates.
            error_class = _error_class(exc)
            logger.warning(
                "llm.call_failed", extra={"error_class": error_class, "error": str(exc)}
            )
            metrics.increment(f"llm.errors.{error_class}")
            raise
        choice = response.choices[0]
        if request.json_schema is not None:
            # Schema adherence does not survive truncation or a safety refusal; surface both so
            # the caller's deterministic fallback engages instead of parsing a broken payload.
            if getattr(choice, "finish_reason", None) == "length":
                raise LlmOutputError(
                    f"structured response truncated at max_tokens ({request.schema_name})"
                )
            refusal = getattr(choice.message, "refusal", None)
            if refusal:
                raise LlmOutputError(f"model refused structured request: {refusal}")
        details = getattr(getattr(response, "usage", None), "prompt_tokens_details", None)
        cached = getattr(details, "cached_tokens", 0) or 0
        return LlmResult(text=str(choice.message.content or ""), cached_prefix_tokens=cached)
