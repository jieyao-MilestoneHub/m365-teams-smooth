"""Outbound clients carry a timeout, and the graph run is bounded by a wall-clock guard."""

from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Any

import pytest

from app.adapters.knowledge.foundry_iq import FoundryIqKnowledgeProvider
from app.adapters.llm.azure_openai import AzureOpenAILLMProvider
from app.agent.runner import CourtRunner
from app.agent.state import CourtState
from app.domain.errors import GraphTimeoutError

_EMPTY: CourtState = {}

# --- outbound client timeouts ---------------------------------------------


def test_azure_openai_forwards_timeout_to_client(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    class _FakeAzure:
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)

    monkeypatch.setattr("app.adapters.llm.azure_openai.AzureOpenAI", _FakeAzure)
    AzureOpenAILLMProvider(
        endpoint="https://e", deployment="d", api_version="v", api_key="k", timeout=5.0
    )
    assert captured["timeout"] == 5.0


class _RecordingRetrieveClient:
    def __init__(self) -> None:
        self.kwargs: dict[str, Any] | None = None

    def retrieve(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        return SimpleNamespace(references=[])


def test_foundry_forwards_timeout_on_retrieve() -> None:
    client = _RecordingRetrieveClient()
    provider = FoundryIqKnowledgeProvider(
        endpoint="https://e",
        knowledge_base_name="kb",
        knowledge_source_name="ks",
        timeout=7.0,
        client=client,  # type: ignore[arg-type]
    )
    provider.ground("a query")
    assert client.kwargs is not None
    assert client.kwargs["timeout"] == 7.0


def test_foundry_omits_timeout_when_unset() -> None:
    client = _RecordingRetrieveClient()
    provider = FoundryIqKnowledgeProvider(
        endpoint="https://e",
        knowledge_base_name="kb",
        knowledge_source_name="ks",
        client=client,  # type: ignore[arg-type]
    )
    provider.ground("a query")
    assert client.kwargs is not None
    assert "timeout" not in client.kwargs


# --- graph wall-clock guard ------------------------------------------------


class _FakeGraph:
    """A graph whose ``invoke`` sleeps for ``invoke_seconds`` before returning."""

    def __init__(self, *, invoke_seconds: float, values: dict[str, object]) -> None:
        self._invoke_seconds = invoke_seconds
        self._values = values
        self.invoked = 0

    def invoke(self, state: Any, config: Any) -> None:
        self.invoked += 1
        time.sleep(self._invoke_seconds)

    def get_state(self, config: Any) -> Any:
        return SimpleNamespace(values=self._values, next=("execute",))

    def update_state(self, config: Any, values: Any) -> None:
        return None


def test_start_raises_typed_error_on_timeout_and_leaves_checkpoint() -> None:
    graph = _FakeGraph(invoke_seconds=0.5, values={"status": "evaluating"})
    runner = CourtRunner(graph, timeout_seconds=0.05)

    with pytest.raises(GraphTimeoutError):
        runner.start("t1", _EMPTY)

    # The checkpoint is still readable (intact and resumable) after the guard fires.
    assert runner.state("t1") == {"status": "evaluating"}


def test_fast_run_completes_within_budget() -> None:
    graph = _FakeGraph(invoke_seconds=0.0, values={"status": "done"})
    runner = CourtRunner(graph, timeout_seconds=5.0)
    result = runner.start("t1", _EMPTY)
    assert result == {"status": "done"}
    assert graph.invoked == 1


def test_no_budget_runs_inline() -> None:
    graph = _FakeGraph(invoke_seconds=0.0, values={"status": "done"})
    runner = CourtRunner(graph)  # timeout_seconds=None
    result = runner.start("t1", _EMPTY)
    assert result == {"status": "done"}
