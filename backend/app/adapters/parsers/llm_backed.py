"""LLM-backed request parser: an LLM turns free text into a structured Change.

Prompts the LLM with the three trial subjects, the registry's capability catalog, and the output
JSON shape, parses the JSON into a Change, and **falls back to the deterministic parser on any
failure** (so it never raises and the trials stay reproducible). The LLMProvider port stays a pure
text generator — the structured contract lives here, not in the port.
"""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

from app.domain import Change, RequestedAction
from app.ports.llm import LLMProvider
from app.ports.registry import IntegrationRegistry
from app.ports.request_parser import RequestParser

_SUBJECTS = {
    "launch": "moving or slipping a launch / milestone / release date",
    "sso-ga": "promising a customer that a feature is generally available by a date",
    "project-access": "granting an external vendor / contractor / agency access to a folder",
}


class _LlmAction(BaseModel):
    system: str
    capability_name: str
    params: dict[str, object] = Field(default_factory=dict)


class _LlmParse(BaseModel):
    subject: str | None = None
    due_by: str | None = None
    actions: list[_LlmAction] = Field(default_factory=list)


def _extract_json(text: str) -> object:
    """Pull the JSON object out of a model response (tolerating code fences and prose)."""
    s = text.strip()
    if s.startswith("```"):
        s = s.strip("`")
        if s[:4].lower() == "json":
            s = s[4:]
    start, end = s.find("{"), s.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object in response")
    return json.loads(s[start : end + 1])


class LlmRequestParser(RequestParser):
    """Parses with an LLM, validating the structure and delegating to a fallback on any failure."""

    def __init__(
        self,
        llm: LLMProvider,
        registry: IntegrationRegistry,
        fallback: RequestParser,
        *,
        today: str | None = None,
    ) -> None:
        self._llm = llm
        self._registry = registry
        self._fallback = fallback
        self._today = today

    def parse(self, raw: str, *, change_id: str) -> Change:
        try:
            text = self._llm.complete(raw, system=self._prompt())
            result = _LlmParse.model_validate(_extract_json(text))
        except Exception:  # noqa: BLE001 — never raise; an unsure LLM falls back to deterministic
            return self._fallback.parse(raw, change_id=change_id)

        if result.subject not in _SUBJECTS:
            return self._fallback.parse(raw, change_id=change_id)

        return Change(
            change_id=change_id,
            raw_request=raw,
            subject=result.subject,
            due_by=result.due_by,
            requested_actions=[
                RequestedAction(
                    system=a.system, capability_name=a.capability_name, params=a.params
                )
                for a in result.actions
            ],
        )

    def _prompt(self) -> str:
        caps = ", ".join(sorted({c.name for c in self._registry.capabilities()}))
        subjects = "; ".join(f"{key} = {meaning}" for key, meaning in _SUBJECTS.items())
        today = self._today or "the current date"
        shape = (
            '{"subject": <one subject or null>, "due_by": <ISO date YYYY-MM-DD or null>, '
            '"actions": [{"system": str, "capability_name": str, "params": object}]}'
        )
        return (
            f"You classify an enterprise change request. Today is {today}.\n"
            f"Choose exactly one subject from: {subjects}.\n"
            "Set due_by to an ISO date (YYYY-MM-DD), resolving relative dates against today; "
            "use null when there is no date.\n"
            f"Use ONLY these capability names for actions: {caps}.\n"
            f"Respond with ONLY a JSON object of this shape: {shape}"
        )
