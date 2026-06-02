"""Composition root: build the court service and its dependencies from settings.

This is the one place concrete adapters are chosen and wired. Gatherers, planners, and rule packs
are injected here; they are empty until Phase 3 fills them, at which point only this file changes.
"""

from __future__ import annotations

from app.adapters.integrations.mock_crm import MockCRMAdapter
from app.adapters.integrations.mock_entra import MockEntraAdapter
from app.adapters.integrations.mock_github import MockGitHubAdapter
from app.adapters.integrations.mock_outlook import MockOutlookAdapter
from app.adapters.integrations.mock_planner import MockPlannerAdapter
from app.adapters.integrations.mock_sharepoint import MockSharePointAdapter
from app.adapters.integrations.mock_teams import MockTeamsAdapter
from app.adapters.integrations.registry import build_registry
from app.adapters.knowledge.fake_knowledge import FakeKnowledgeProvider
from app.adapters.persistence.checkpointer import SqliteCheckpointStore
from app.adapters.persistence.db import init_db, make_engine, make_session_factory
from app.adapters.persistence.repositories import SqlAuditRepository, SqlVerdictLedger
from app.agent.gatherers import GATHERERS
from app.agent.graph import build_court_graph
from app.agent.nodes.audit import AuditNode
from app.agent.nodes.execute import ExecuteNode
from app.agent.nodes.impact import Gatherer, ImpactNode
from app.agent.nodes.intake import IntakeNode
from app.agent.nodes.options import OptionsNode, Planner
from app.agent.nodes.policy import PolicyNode, RulePackQuorumResolver
from app.agent.planners import PLANNERS
from app.agent.policy_rules.models import RulePack
from app.agent.policy_rules.packs import default_packs
from app.agent.runner import CourtRunner
from app.config import Settings
from app.ports.integration import IntegrationAdapter
from app.ports.registry import IntegrationRegistry
from app.services.court_service import CourtService


def build_court_service(
    settings: Settings,
    *,
    gatherers: dict[str, Gatherer] | None = None,
    planners: dict[str, Planner] | None = None,
    packs: list[RulePack] | None = None,
    registry: IntegrationRegistry | None = None,
) -> CourtService:
    """Wire the registry, providers, persistence, graph, and runner into a CourtService.

    Gatherers, planners, and packs default to the three-trial configuration; pass explicit values
    (including empty collections) to override — e.g. ``packs=[]`` for an approval-free court. A
    ``registry`` override allows tests to inject adapters (e.g. with a failure injected).
    """
    gatherers = gatherers if gatherers is not None else GATHERERS
    planners = planners if planners is not None else PLANNERS
    packs = packs if packs is not None else default_packs()

    if registry is None:
        candidates: dict[str, dict[str, IntegrationAdapter]] = {
            "github": {"mock": MockGitHubAdapter()},
            "outlook": {"mock": MockOutlookAdapter()},
            "planner": {"mock": MockPlannerAdapter()},
            "sharepoint": {"mock": MockSharePointAdapter()},
            "teams": {"mock": MockTeamsAdapter()},
            "crm": {"mock": MockCRMAdapter()},
            "entra": {"mock": MockEntraAdapter()},
        }
        registry = build_registry(settings, candidates)
    knowledge = FakeKnowledgeProvider()

    engine = make_engine(settings.db_url)
    init_db(engine)
    session_factory = make_session_factory(engine)
    audit_repo = SqlAuditRepository(session_factory)
    ledger = SqlVerdictLedger(session_factory)

    store = SqliteCheckpointStore.from_db_url(settings.db_url)
    store.setup()

    graph = build_court_graph(
        intake=IntakeNode(registry),
        impact=ImpactNode(registry, knowledge, gatherers),
        options=OptionsNode(planners),
        policy=PolicyNode(packs, RulePackQuorumResolver()),
        execute=ExecuteNode(registry),
        audit=AuditNode(audit_repo),
        checkpointer=store.saver(),
    )
    runner = CourtRunner(graph)
    return CourtService(
        runner,
        audit_repo,
        ledger,
        registry=registry,
        dry_run_default=settings.dry_run_default,
    )
