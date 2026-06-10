"""Prompt caching: stable prefixes lead, volatile text follows, cache hits surface."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

from app.adapters.llm.azure_openai import AzureOpenAILLMProvider
from app.adapters.parsers.deterministic import DeterministicRequestParser
from app.adapters.parsers.llm_backed import LlmRequestParser
from app.agent.agentic.planner import LlmPlanner
from app.domain import (
    Capability,
    CapabilityKind,
    CapabilityRef,
    Change,
    ExecutionPlan,
    ExecutionStep,
    ImpactEvidence,
    PlanKind,
)
from app.ports.llm import LLMProvider, LlmRequest, LlmResult


class _RecordingLLM(LLMProvider):
    """Captures every LlmRequest passed through generate()."""

    def __init__(self, response: str) -> None:
        self._response = response
        self.requests: list[LlmRequest] = []

    def complete(self, prompt: str, *, system: str | None = None) -> str:
        return self._response

    def generate(self, request: LlmRequest) -> LlmResult:
        self.requests.append(request)
        return LlmResult(text=self._response)


# --- adapter: message layout and cache-hit readback -----------------------------------------


def _client(response: Any) -> Any:
    holder = SimpleNamespace(kwargs={})

    def create(**kwargs: Any) -> Any:
        holder.kwargs = kwargs
        return response

    holder.chat = SimpleNamespace(completions=SimpleNamespace(create=create))
    return holder


def _response(cached_tokens: int | None = None) -> Any:
    message = SimpleNamespace(content="ok", refusal=None)
    usage = None
    if cached_tokens is not None:
        usage = SimpleNamespace(prompt_tokens_details=SimpleNamespace(cached_tokens=cached_tokens))
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message, finish_reason="stop")], usage=usage
    )


def _provider(client: Any) -> AzureOpenAILLMProvider:
    return AzureOpenAILLMProvider(
        endpoint="https://x", deployment="gpt-4o", api_version="2024-10-21", client=client
    )


def test_prefix_leads_and_suffix_follows_as_separate_system_messages() -> None:
    client = _client(_response())
    _provider(client).generate(
        LlmRequest(prompt="user text", cacheable_prefix="STATIC CATALOG", system_suffix="stance")
    )
    assert client.kwargs["messages"] == [
        {"role": "system", "content": "STATIC CATALOG"},
        {"role": "system", "content": "stance"},
        {"role": "user", "content": "user text"},
    ]


def test_cached_tokens_surface_on_the_result() -> None:
    client = _client(_response(cached_tokens=1536))
    result = _provider(client).generate(LlmRequest(prompt="p", cacheable_prefix="catalog"))
    assert result.cached_prefix_tokens == 1536


def test_missing_usage_reads_as_zero_cache_hits() -> None:
    client = _client(_response())
    assert _provider(client).generate(LlmRequest(prompt="p")).cached_prefix_tokens == 0


# --- call sites: the volatile parts stay out of the cacheable prefix -------------------------


def _write_cap() -> Capability:
    return Capability(
        system="github",
        name="github.update_milestone_due",
        kind=CapabilityKind.WRITE,
        description="d",
        params_schema={},
    )


def _baseline(kind: PlanKind) -> ExecutionPlan:
    return ExecutionPlan(
        kind=kind,
        steps=[
            ExecutionStep(
                step_id="b1",
                capability=CapabilityRef(system="github", name="github.update_milestone_due"),
                params={},
            )
        ],
        rationale="baseline",
        supersedes_request=kind is PlanKind.SAFE_ALTERNATIVE,
    )


class _Registry:
    def capabilities(self) -> list[Capability]:
        return [_write_cap()]

    def get(self, system: str) -> None:
        return None


def _planner_request(kind: PlanKind) -> LlmRequest:
    reply = json.dumps(
        {"steps": [{"system": "github", "name": "github.update_milestone_due", "params": {}}],
         "rationale": "r"}
    )
    llm = _RecordingLLM(reply)
    planner = LlmPlanner(llm, _Registry(), fallback=lambda c, i: _baseline(kind))  # type: ignore[arg-type]
    planner(Change(change_id="c1", raw_request="slip the launch", subject="launch"),
            ImpactEvidence())
    return llm.requests[0]


def test_planner_prefix_is_stable_across_plan_kinds() -> None:
    feasible = _planner_request(PlanKind.FEASIBLE)
    refused = _planner_request(PlanKind.SAFE_ALTERNATIVE)
    assert feasible.cacheable_prefix == refused.cacheable_prefix
    assert feasible.system_suffix != refused.system_suffix
    assert "REFUSED" in (refused.system_suffix or "")
    assert "REFUSED" not in (feasible.cacheable_prefix or "")


def _parser_request(today: str) -> LlmRequest:
    reply = json.dumps({"subject": "launch", "due_by": None, "actions": []})
    llm = _RecordingLLM(reply)
    parser = LlmRequestParser(llm, _Registry(), DeterministicRequestParser(), today=today)  # type: ignore[arg-type]
    parser.parse("push the launch out a week", change_id="c1")
    return llm.requests[0]


def test_parser_prefix_is_stable_across_days() -> None:
    monday = _parser_request("2026-06-08")
    tuesday = _parser_request("2026-06-09")
    assert monday.cacheable_prefix == tuesday.cacheable_prefix
    assert "2026-06-08" not in (monday.cacheable_prefix or "")
    assert monday.system_suffix == "Today is 2026-06-08."
    assert tuesday.system_suffix == "Today is 2026-06-09."
