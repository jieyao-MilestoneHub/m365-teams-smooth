"""The LLM-backed parser maps model JSON to a Change, validates downstream, and falls back."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

from app.adapters.llm.azure_openai import AzureOpenAILLMProvider
from app.adapters.parsers.deterministic import DeterministicRequestParser
from app.adapters.parsers.llm_backed import LlmRequestParser
from app.agent.nodes.intake import IntakeNode
from app.agent.state import CourtState, initial_state
from app.domain import Change, ChangeStatus, RunMode
from app.ports.llm import LLMProvider


class _StubLLM(LLMProvider):
    """Returns a canned completion regardless of the prompt."""

    def __init__(self, reply: str) -> None:
        self._reply = reply

    def complete(self, prompt: str, *, system: str | None = None) -> str:
        return self._reply


def _state(raw: str) -> CourtState:
    return initial_state(
        thread_id="t1", change_id="c1", raw_request=raw, source="test", run_mode=RunMode.DRY_RUN
    )


def test_llm_json_maps_to_a_change(mock_registry: Any) -> None:
    reply = json.dumps(
        {
            "subject": "sso-ga",
            "due_by": "2026-06-17",
            "actions": [],
        }
    )
    parser = LlmRequestParser(_StubLLM(reply), mock_registry, DeterministicRequestParser())
    change = parser.parse("can we tell the customer SSO ships next Wednesday?", change_id="c1")
    assert change.subject == "sso-ga"
    assert change.due_by == "2026-06-17"


def test_llm_path_is_registry_validated_through_intake(mock_registry: Any) -> None:
    # One valid action + one unsupported action; the intake guard drops the unsupported one.
    reply = json.dumps(
        {
            "subject": "launch",
            "due_by": "2026-06-17",
            "actions": [
                {"system": "github", "capability_name": "github.update_milestone_due",
                 "params": {"milestone": "Launch", "due_on": "2026-06-17"}},
                {"system": "github", "capability_name": "github.delete_repo", "params": {}},
            ],
        }
    )
    parser = LlmRequestParser(_StubLLM(reply), mock_registry, DeterministicRequestParser())
    result = IntakeNode(parser, mock_registry)(_state("push the launch out a week"))
    change = Change.model_validate(result["change"])
    names = [a.capability_name for a in change.requested_actions]
    assert "github.update_milestone_due" in names
    assert "github.delete_repo" not in names  # unregistered -> dropped by the guard
    assert any("github.delete_repo" in e for e in result["errors"])


def test_garbage_response_falls_back_to_deterministic(mock_registry: Any) -> None:
    parser = LlmRequestParser(
        _StubLLM("sorry, I cannot help"), mock_registry, DeterministicRequestParser()
    )
    change = parser.parse("slip the launch from 2026-06-10 to 2026-06-17", change_id="c1")
    # fell back to deterministic, which still routes correctly
    assert change.subject == "launch"
    assert change.due_by == "2026-06-17"


def test_unknown_subject_falls_back(mock_registry: Any) -> None:
    parser = LlmRequestParser(_StubLLM('{"subject": "weather", "actions": []}'), mock_registry,
                              DeterministicRequestParser())
    change = parser.parse("give the vendor access to Project X", change_id="c1")
    assert change.subject == "project-access"  # deterministic fallback


def test_llm_blocks_when_intake_finds_no_supported_action(mock_registry: Any) -> None:
    parser = LlmRequestParser(_StubLLM('{"subject": "sso-ga", "actions": []}'), mock_registry,
                              DeterministicRequestParser())
    result = IntakeNode(parser, mock_registry)(_state("promise the customer SSO by friday"))
    # sso-ga has no requested actions, so nothing to reject -> proceeds (not blocked)
    assert result["status"] == ChangeStatus.EVALUATING.value


def test_azure_provider_uses_injected_client() -> None:
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="hi from azure"))]
    )
    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **_: response))
    )
    provider = AzureOpenAILLMProvider(
        endpoint="https://x", deployment="gpt-4o", api_version="2024-10-21", client=client
    )
    assert provider.complete("hello", system="be terse") == "hi from azure"
