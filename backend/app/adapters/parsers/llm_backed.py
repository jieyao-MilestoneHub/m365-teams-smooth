"""LLM-backed request parser: an LLM turns free text into a structured Change.

Prompts the LLM with the trial subjects, the registry's capability catalog, and a strict JSON
schema (engaged natively by providers that support structured output, ignored by the offline fake),
parses the JSON into a Change, and **falls back to the deterministic parser on any failure** (so it
never raises and the trials stay reproducible).
"""

from __future__ import annotations

import logging
import re

from pydantic import BaseModel, Field, field_validator

from app.domain import Change, RequestedAction
from app.llm.structured import decode_json_object, parse_json, schema_of
from app.llm.untrusted import HARDENING, fence
from app.observability import metrics
from app.ports.guardrail import GuardrailPort
from app.ports.llm import LLMProvider, LlmRequest
from app.ports.registry import IntegrationRegistry
from app.ports.request_parser import RequestParser

logger = logging.getLogger(__name__)

# Subjects with specialized handling (scenario gatherers/planners/grounding). They are prompt
# hints, not a gate: the LLM may coin a new kebab-case subject for anything else, and that parse
# is kept — the policy floor governs whatever no pack matches.
_KNOWN_SUBJECTS = {
    "launch": "moving or slipping a launch / milestone / release date",
    "sso-ga": "promising a customer that a feature is generally available by a date",
    "project-access": "granting an external vendor / contractor / agency access to a folder",
    "meeting-actions": "turning meeting or standup discussion into tracked follow-up tasks",
    "weekly-report": "aggregating recent project activity into a status report for the channel",
}

_SUBJECT_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


class _LlmAction(BaseModel):
    system: str
    capability_name: str
    params: dict[str, object] = Field(default_factory=dict)

    # In strict structured-output mode the free-form params object travels JSON-encoded.
    @field_validator("params", mode="before")
    @classmethod
    def _decode_params(cls, value: object) -> object:
        return decode_json_object(value)


class _LlmParse(BaseModel):
    subject: str | None = None
    due_by: str | None = None
    actions: list[_LlmAction] = Field(default_factory=list)

    # A malformed subject degrades to unclassified (the parse — and its actions — is kept);
    # only a parse failure or a guardrail block falls back to the deterministic parser.
    @field_validator("subject", mode="before")
    @classmethod
    def _normalize_subject(cls, value: object) -> object:
        if not isinstance(value, str):
            return None
        slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")[:64]
        return slug if _SUBJECT_RE.fullmatch(slug) else None


_PARSE_SCHEMA = schema_of(_LlmParse)


class LlmRequestParser(RequestParser):
    """Parses with an LLM, validating the structure and delegating to a fallback on any failure."""

    def __init__(
        self,
        llm: LLMProvider,
        registry: IntegrationRegistry,
        fallback: RequestParser,
        *,
        today: str | None = None,
        guardrail: GuardrailPort | None = None,
        guardrail_blocking: bool = True,
    ) -> None:
        self._llm = llm
        self._registry = registry
        self._fallback = fallback
        self._today = today
        self._guardrail = guardrail
        self._block = guardrail_blocking

    def parse(self, raw: str, *, change_id: str) -> Change:
        # The raw request is untrusted; screen it and isolate it from the instructions.
        if self._guardrail is not None and self._block:
            verdict = self._guardrail.screen_input(user_text=raw)
            if verdict.flagged:
                logger.warning("parser.guardrail_blocked", extra={"cats": verdict.categories})
                metrics.increment("guardrail.input_blocked")
                return self._fallback.parse(raw, change_id=change_id)
        try:
            text = self._llm.generate(
                LlmRequest(
                    prompt=fence("request", raw),
                    cacheable_prefix=self._prompt(),
                    system_suffix=self._today_suffix(),
                    json_schema=_PARSE_SCHEMA,
                    schema_name="change_parse",
                )
            ).text
            result = _LlmParse.model_validate(parse_json(text))
        except Exception as exc:  # noqa: BLE001 — never raise; an unsure LLM falls back
            logger.warning(
                "parser.llm_fallback", extra={"reason": "parse_error", "error": str(exc)}
            )
            metrics.increment("parser.llm_fallback")
            return self._fallback.parse(raw, change_id=change_id)

        change = Change(
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
        # For a KNOWN subject, a parse whose actions would all be rejected by intake's guard (an
        # unregistered capability or missing required params) reaches the pipeline as a BLOCKED
        # trial — yet the deterministic parser produces well-formed actions for exactly these
        # subjects. Fall back rather than block, so the LLM omitting an action's params never
        # refuses a valid change. A NOVEL subject's parse is kept as-is (a classification, not a
        # failure): the ungoverned floor governs it and intake drops any unusable action.
        if (
            change.subject in _KNOWN_SUBJECTS
            and change.requested_actions
            and not self._has_valid_action(change.requested_actions)
        ):
            logger.warning("parser.llm_fallback", extra={"reason": "known_subject_actions_invalid"})
            metrics.increment("parser.llm_fallback")
            return self._fallback.parse(raw, change_id=change_id)
        return change

    def _has_valid_action(self, actions: list[RequestedAction]) -> bool:
        """True when at least one proposed action passes the registry's capability validation."""
        for action in actions:
            adapter = self._registry.get(action.system)
            if adapter is None:
                continue
            try:
                adapter.validate(action)
                return True
            except Exception:  # noqa: BLE001 — any validation failure means this action is unusable
                continue
        return False

    def _prompt(self) -> str:
        """The stable instruction block (catalog, subjects, shape) — a cacheable prefix."""
        caps = ", ".join(sorted({c.name for c in self._registry.capabilities()}))
        subjects = "; ".join(f"{key} = {meaning}" for key, meaning in _KNOWN_SUBJECTS.items())
        shape = (
            '{"subject": <one subject or null>, "due_by": <ISO date YYYY-MM-DD or null>, '
            '"actions": [{"system": str, "capability_name": str, '
            'params: JSON-encoded object string}]}'
        )
        return (
            "You classify an enterprise change request.\n"
            f"{HARDENING}\n"
            "Classify the request with a subject. Prefer one of these known subjects when the "
            f"request clearly fits: {subjects}. Otherwise coin a short, specific kebab-case "
            'subject (e.g. "database-migration"); use null only when no subject is '
            "identifiable.\n"
            "Set due_by to an ISO date (YYYY-MM-DD), resolving relative dates against today's "
            "date (stated separately); use null when there is no date.\n"
            f"Use ONLY these capability names for actions: {caps}.\n"
            f"Respond with ONLY a JSON object of this shape: {shape}"
        )

    def _today_suffix(self) -> str:
        """The volatile date line — kept out of the cacheable prefix."""
        return f"Today is {self._today or 'the current date'}."
