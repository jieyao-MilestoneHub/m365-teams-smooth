"""Boundary validation, error capping, and graceful knowledge degradation.

Inputs are rejected at the service edge (never truncated), the per-checkpoint error list stays
bounded, and a failing knowledge provider costs the trial its citations — not the trial.
"""

from __future__ import annotations

import pytest

from app.agent.state import MAX_ERRORS, bound_errors
from app.config import Settings
from app.container import build_court_service
from app.domain import GroundedFact
from app.domain.errors import InvalidRequestError
from app.ports.knowledge import KnowledgePort
from app.services.court_service import CourtService


def _service(**overrides: object) -> CourtService:
    settings = Settings(
        force_all_mock=True, db_url="sqlite:///:memory:", dry_run_default=True
    )
    return build_court_service(settings, **overrides)  # type: ignore[arg-type]


def test_blank_request_is_rejected() -> None:
    with pytest.raises(InvalidRequestError):
        _service().submit_change("   ")


def test_oversized_request_is_rejected_not_truncated() -> None:
    service = _service()
    with pytest.raises(InvalidRequestError) as excinfo:
        service.submit_change("slip the launch " * 100)  # ~1600 chars > the 1000 default
    assert "1000" in str(excinfo.value)


def test_demo_requests_fit_within_the_bound() -> None:
    service = _service()
    summary = service.submit_change("promise Customer A that SSO is GA by 2026-06-17")
    assert summary.status == "awaiting_verdict"


def test_bound_errors_caps_with_a_truncation_marker() -> None:
    errors = [f"e{i}" for i in range(MAX_ERRORS + 25)]
    bounded = bound_errors(errors)
    assert len(bounded) == MAX_ERRORS + 1
    assert bounded[-1] == "... 25 further errors truncated"
    assert bound_errors(["one"]) == ["one"]


def test_bound_evidence_caps_and_keeps_high_severity() -> None:
    from app.agent.state import MAX_EVIDENCE_ITEMS, bound_evidence
    from app.domain import EvidenceItem

    high = [EvidenceItem(system="s", kind="decisive", summary=f"h{i}", severity="high")
            for i in range(3)]
    noise = [
        EvidenceItem(system="s", kind="agentic", summary=f"n{i}")
        for i in range(MAX_EVIDENCE_ITEMS + 20)
    ]
    bounded = bound_evidence([*high, *noise])

    assert len(bounded) == MAX_EVIDENCE_ITEMS  # total capped (kept items + one truncation marker)
    assert all(h in bounded for h in high)  # every high-severity finding is kept
    assert bounded[-1].kind == "truncation"
    assert "truncated" in bounded[-1].summary
    # A small list is returned untouched.
    assert bound_evidence(high) == high


class _ExplodingKnowledge(KnowledgePort):
    def ground(self, query: str, *, top_k: int = 3) -> list[GroundedFact]:
        raise RuntimeError("search service unavailable")


def test_knowledge_failure_degrades_to_an_error_not_a_crash() -> None:
    from app.agent.nodes.impact import ImpactNode
    from app.agent.state import initial_state, serialize
    from app.domain import Change, RunMode

    class _Registry:
        def get(self, system: str) -> None:
            return None

        def capabilities(self) -> list[object]:
            return []

    node = ImpactNode(_Registry(), _ExplodingKnowledge(), {})  # type: ignore[arg-type]
    state = initial_state(
        thread_id="t1", change_id="c1", raw_request="slip", source="t", run_mode=RunMode.DRY_RUN
    )
    state["change"] = serialize(Change(change_id="c1", raw_request="slip"))

    update = node(state)

    assert update["status"] == "evaluating"  # the trial proceeds
    assert any("knowledge grounding unavailable" in e for e in update["errors"])


def test_llm_prompt_stays_bounded_for_a_maximal_request() -> None:
    """Prompt-size regression guard: a maximal legal request yields a bounded prompt."""
    from app.adapters.parsers.deterministic import DeterministicRequestParser
    from app.adapters.parsers.llm_backed import LlmRequestParser
    from app.ports.llm import LLMProvider

    class _RecordingLLM(LLMProvider):
        def __init__(self) -> None:
            self.prompts: list[tuple[str, str]] = []

        def complete(self, prompt: str, *, system: str | None = None) -> str:
            self.prompts.append((prompt, system or ""))
            return "not json"  # forces the deterministic fallback; recording is the point

    class _Registry:
        def capabilities(self) -> list[object]:
            return []

    llm = _RecordingLLM()
    parser = LlmRequestParser(
        llm, _Registry(), fallback=DeterministicRequestParser(today="2026-06-04")  # type: ignore[arg-type]
    )
    max_request = "x" * Settings().max_request_chars  # the largest input the boundary admits
    parser.parse(max_request, change_id="c1")

    prompt, system = llm.prompts[0]
    # User prompt is the (bounded) request wrapped in a fixed-size untrusted-data fence; the system
    # prompt is a fixed template (incl. the injection-hardening line) plus the capability catalog —
    # small and registry-sized, not input-sized.
    assert len(prompt) < Settings().max_request_chars + 100  # request + constant fence overhead
    assert len(system) < 4000
