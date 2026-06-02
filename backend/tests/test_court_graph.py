"""End-to-end Phase 2: the court runs to the verdict gate, resumes, and is idempotent.

Wired with the real nodes and a minimal rule pack so the whole pipeline executes under a mocked,
credential-free environment — the Phase 2 definition of done.
"""

from __future__ import annotations

from typing import Any

from app.adapters.knowledge.fake_knowledge import FakeKnowledgeProvider
from app.adapters.persistence.checkpointer import SqliteCheckpointStore
from app.agent.graph import build_court_graph
from app.agent.nodes.audit import AuditNode
from app.agent.nodes.execute import ExecuteNode
from app.agent.nodes.impact import ImpactNode
from app.agent.nodes.intake import IntakeNode
from app.agent.nodes.options import OptionsNode
from app.agent.nodes.policy import PolicyNode
from app.agent.policy_rules.models import (
    MatchRules,
    RiskBands,
    RiskFactorRule,
    RulePack,
    VerdictOptionRules,
)
from app.agent.runner import CourtRunner
from app.agent.state import initial_state
from app.domain import (
    Change,
    ChangeStatus,
    ImpactEvidence,
    RunMode,
    Verdict,
    VerdictType,
)
from app.ports.knowledge import KnowledgePort
from app.ports.registry import IntegrationRegistry
from tests.conftest import (
    InMemoryAuditRepository,
    build_mock_registry,
)

_PACK = RulePack(
    id="launch_slip",
    match=MatchRules(any_action_capability=["github.update_milestone_due"]),
    risk_factors=[
        RiskFactorRule(id="milestone_move", when_tag="schedule.milestone_move", weight=80)
    ],
    risk_bands=RiskBands(low=0, medium=30, high=60),
    verdict_options=VerdictOptionRules(default=[VerdictType.APPROVE, VerdictType.REJECT]),
)


def _launch_gatherer(
    change: Change, registry: IntegrationRegistry, knowledge: KnowledgePort
) -> ImpactEvidence:
    return ImpactEvidence(tags=["schedule.milestone_move"])


def _build(audit_repo: InMemoryAuditRepository, store: SqliteCheckpointStore) -> Any:
    registry = build_mock_registry()
    knowledge = FakeKnowledgeProvider()
    return build_court_graph(
        intake=IntakeNode(registry),
        impact=ImpactNode(registry, knowledge, {"launch": _launch_gatherer}),
        options=OptionsNode({}),
        policy=PolicyNode([_PACK]),
        execute=ExecuteNode(registry),
        audit=AuditNode(audit_repo),
        checkpointer=store.saver(),
    )


def _start_state(thread_id: str) -> Any:
    return initial_state(
        thread_id=thread_id,
        change_id="c1",
        raw_request="slip the launch from 2026-06-10 to 2026-06-17",
        source="test",
        run_mode=RunMode.DRY_RUN,
    )


def test_run_suspends_at_verdict_then_resumes_to_done() -> None:
    repo = InMemoryAuditRepository()
    store = SqliteCheckpointStore(":memory:")
    store.setup()
    runner = CourtRunner(_build(repo, store))

    state = runner.start("t1", _start_state("t1"))
    assert state["status"] == ChangeStatus.AWAITING_VERDICT.value
    assert runner.is_awaiting_verdict("t1")
    assert repo.records == []  # nothing audited before the verdict

    verdict = Verdict(verdict_id="v1", type=VerdictType.APPROVE, idempotency_key="k1")
    resumed = runner.resume("t1", verdict)
    assert resumed["status"] == ChangeStatus.DONE.value
    assert len(repo.records) == 1
    # dry-run: the audit is marked DRY_RUN and the step predicted rather than applied
    assert repo.records[0].run_mode is RunMode.DRY_RUN


def test_resume_is_idempotent_at_runner_level() -> None:
    repo = InMemoryAuditRepository()
    store = SqliteCheckpointStore(":memory:")
    store.setup()
    runner = CourtRunner(_build(repo, store))
    runner.start("t1", _start_state("t1"))

    verdict = Verdict(verdict_id="v1", type=VerdictType.APPROVE, idempotency_key="k1")
    runner.resume("t1", verdict)
    runner.resume("t1", verdict)  # second resume must not execute again

    assert len(repo.records) == 1


def test_fresh_runner_resumes_from_checkpoint() -> None:
    repo = InMemoryAuditRepository()
    store = SqliteCheckpointStore(":memory:")
    store.setup()
    CourtRunner(_build(repo, store)).start("t1", _start_state("t1"))

    # A brand-new graph + runner sharing only the checkpoint store resumes the run.
    fresh = CourtRunner(_build(repo, store))
    verdict = Verdict(verdict_id="v1", type=VerdictType.APPROVE, idempotency_key="k1")
    resumed = fresh.resume("t1", verdict)
    assert resumed["status"] == ChangeStatus.DONE.value
