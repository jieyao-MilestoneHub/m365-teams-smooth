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

from typing import Any

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from openai import AzureOpenAI

from app.domain.errors import LlmOutputError
from app.ports.llm import LLMProvider, LlmRequest, LlmResult

_SCOPE = "https://cognitiveservices.azure.com/.default"


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
            )
        else:
            token_provider = get_bearer_token_provider(DefaultAzureCredential(), _SCOPE)
            self._client = AzureOpenAI(
                azure_endpoint=endpoint,
                api_version=api_version,
                azure_ad_token_provider=token_provider,
                timeout=timeout,
            )

    def complete(self, prompt: str, *, system: str | None = None) -> str:
        return self.generate(LlmRequest(prompt=prompt, cacheable_prefix=system)).text

    def generate(self, request: LlmRequest) -> LlmResult:
        messages: list[dict[str, str]] = []
        system = "\n".join(p for p in (request.cacheable_prefix, request.system_suffix) if p)
        if system:
            messages.append({"role": "system", "content": system})
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
        response = self._client.chat.completions.create(
            model=self._deployment,
            messages=messages,
            temperature=0,
            max_tokens=request.max_tokens or self._max_tokens,
            **extra,
        )
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
        return LlmResult(text=str(choice.message.content or ""))
