"""Real LLM provider: Azure OpenAI chat completions, behind the LLMProvider port.

Satisfies the LLMProvider port (free-text generation). Auth is keyless (``DefaultAzureCredential``
bearer token) unless an API key is given; an injected ``client`` is accepted for tests (mirrors the
Foundry IQ provider). Selected in the composition root only when an endpoint + deployment are set;
otherwise the offline FakeLLMProvider stays the default, so the trials remain credential-free.
"""

from __future__ import annotations

from typing import Any

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from openai import AzureOpenAI

from app.ports.llm import LLMProvider

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
        client: Any | None = None,
    ) -> None:
        self._deployment = deployment
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
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        response = self._client.chat.completions.create(
            model=self._deployment, messages=messages, temperature=0
        )
        return str(response.choices[0].message.content or "")
