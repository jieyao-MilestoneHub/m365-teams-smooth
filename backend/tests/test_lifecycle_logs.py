"""Lifecycle logs: the meaningful events fire at the right level across service and adapters."""

from __future__ import annotations

import logging

import pytest

from app.adapters.integrations.mock_github import MockGitHubAdapter
from app.adapters.integrations.registry import ConfigIntegrationRegistry, select_adapters
from app.adapters.parsers.deterministic import DeterministicRequestParser
from app.adapters.parsers.llm_backed import LlmRequestParser
from app.agent.nodes.execute import ExecuteNode
from app.agent.policy_rules.models import (
    ApproverRule,
    MatchRules,
    QuorumRules,
    RiskBands,
    RiskFactorRule,
    RulePack,
    VerdictOptionRules,
)
from app.agent.state import CourtState, initial_state, serialize
from app.config import Settings
from app.container import build_court_service
from app.domain import (
    ApproverRole,
    CapabilityRef,
    Change,
    ExecutionPlan,
    ExecutionStep,
    ImpactEvidence,
    PlanKind,
    RunMode,
    Verdict,
    VerdictType,
)
from app.ports.integration import IntegrationAdapter
from app.ports.knowledge import KnowledgePort
from app.ports.llm import LLMProvider
from app.ports.registry import IntegrationRegistry
from tests.conftest import ALL_ROLE_DIRECTORY, APPROVER, REQUESTER

_PACK = RulePack(
    id="launch_slip",
    match=MatchRules(any_action_capability=["github.update_milestone_due"]),
    risk_factors=[
        RiskFactorRule(id="milestone_move", when_tag="schedule.milestone_move", weight=80)
    ],
    risk_bands=RiskBands(low=0, medium=30, high=60),
    # A required role lets an authorized approver cast the verdict (and re-cast it for the
    # duplicate path) — the log events under test.
    quorum=QuorumRules(
        approvers=[ApproverRule(role=ApproverRole.ENG_LEAD, when_tag="schedule.milestone_move")]
    ),
    verdict_options=VerdictOptionRules(default=[VerdictType.APPROVE, VerdictType.REJECT]),
)


def _gatherer(
    change: Change, registry: IntegrationRegistry, knowledge: KnowledgePort, errors: list[str]
) -> ImpactEvidence:
    return ImpactEvidence(tags=["schedule.milestone_move"])


def _settings() -> Settings:
    return Settings(
        force_all_mock=True,
        db_url="sqlite:///:memory:",
        dry_run_default=True,
        approver_directory=ALL_ROLE_DIRECTORY,
    )


def _levels(caplog: pytest.LogCaptureFixture, message: str) -> list[str]:
    return [r.levelname for r in caplog.records if r.getMessage() == message]


class _StubLLM(LLMProvider):
    def __init__(self, reply: str) -> None:
        self._reply = reply

    def complete(self, prompt: str, *, system: str | None = None) -> str:
        return self._reply


def test_submit_and_verdict_events(caplog: pytest.LogCaptureFixture) -> None:
    service = build_court_service(_settings(), gatherers={"launch": _gatherer}, packs=[_PACK])

    with caplog.at_level(logging.INFO):
        summary = service.submit_change(
            "slip the launch from 2026-06-10 to 2026-06-17", requester=REQUESTER
        )
        cast = service.cast_verdict(summary.thread_id, VerdictType.APPROVE, principal=APPROVER)
        service.cast_verdict(summary.thread_id, VerdictType.APPROVE, principal=APPROVER)

    assert cast.audit_id is not None
    assert _levels(caplog, "trial.submitted") == ["INFO"]
    assert _levels(caplog, "verdict.cast") == ["INFO"]
    assert _levels(caplog, "verdict.duplicate") == ["INFO"]


def _execute_state(registry_plan: ExecutionPlan) -> CourtState:
    state = initial_state(
        thread_id="t1", change_id="c1", raw_request="x", source="t", run_mode=RunMode.DRY_RUN
    )
    state["options"] = serialize(registry_plan)
    state["verdict"] = serialize(
        Verdict(verdict_id="v1", type=VerdictType.APPROVE, idempotency_key="k")
    )
    return state


def _github_plan() -> ExecutionPlan:
    return ExecutionPlan(
        kind=PlanKind.FEASIBLE,
        steps=[
            ExecutionStep(
                step_id="s1",
                capability=CapabilityRef(system="github", name="github.update_milestone_due"),
                params={"milestone": "Launch", "due_on": "2026-06-17"},
            )
        ],
    )


def test_step_failed_logged_as_warning_when_no_adapter(caplog: pytest.LogCaptureFixture) -> None:
    node = ExecuteNode(ConfigIntegrationRegistry([]))  # empty registry -> no adapter for the step

    with caplog.at_level(logging.INFO):
        node(_execute_state(_github_plan()))

    assert _levels(caplog, "step.failed") == ["WARNING"]


def test_step_ok_logged_as_info(caplog: pytest.LogCaptureFixture) -> None:
    node = ExecuteNode(ConfigIntegrationRegistry([MockGitHubAdapter()]))

    with caplog.at_level(logging.INFO):
        node(_execute_state(_github_plan()))

    assert _levels(caplog, "step.ok") == ["INFO"]


def test_adapter_selection_and_fallback(caplog: pytest.LogCaptureFixture) -> None:
    # Request github:real, but only a mock candidate exists -> fall back with a warning.
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        force_all_mock=False,
        integration_mode="github:real",
        db_url="sqlite:///:memory:",
    )
    candidates: dict[str, dict[str, IntegrationAdapter]] = {
        "github": {"mock": MockGitHubAdapter()}
    }

    with caplog.at_level(logging.INFO):
        select_adapters(settings, candidates)

    assert _levels(caplog, "adapter.fallback") == ["WARNING"]
    assert _levels(caplog, "adapter.selected") == ["INFO"]


def test_parser_fallback_on_garbage_and_unknown_subject(
    caplog: pytest.LogCaptureFixture, mock_registry: ConfigIntegrationRegistry
) -> None:
    deterministic = DeterministicRequestParser()

    with caplog.at_level(logging.WARNING):
        LlmRequestParser(_StubLLM("not json at all"), mock_registry, deterministic).parse(
            "slip the launch from 2026-06-10 to 2026-06-17", change_id="c1"
        )
        LlmRequestParser(_StubLLM('{"subject": "bogus"}'), mock_registry, deterministic).parse(
            "slip the launch from 2026-06-10 to 2026-06-17", change_id="c2"
        )

    reasons = [
        r.__dict__.get("reason")
        for r in caplog.records
        if r.getMessage() == "parser.llm_fallback"
    ]
    assert "parse_error" in reasons
    assert "unknown_subject" in reasons
    assert _levels(caplog, "parser.llm_fallback") == ["WARNING", "WARNING"]
