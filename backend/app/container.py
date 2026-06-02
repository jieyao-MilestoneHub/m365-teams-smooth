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
from app.adapters.integrations.real_github import RealGitHubAdapter
from app.adapters.integrations.registry import build_registry
from app.adapters.knowledge.fake_knowledge import FakeKnowledgeProvider
from app.adapters.knowledge.foundry_iq import FoundryIqKnowledgeProvider
from app.adapters.parsers.deterministic import DeterministicRequestParser
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
from app.ports.knowledge import KnowledgePort
from app.ports.registry import IntegrationRegistry
from app.ports.request_parser import RequestParser
from app.services.court_service import CourtService


def build_court_service(
    settings: Settings,
    *,
    gatherers: dict[str, Gatherer] | None = None,
    planners: dict[str, Planner] | None = None,
    packs: list[RulePack] | None = None,
    registry: IntegrationRegistry | None = None,
    request_parser: RequestParser | None = None,
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
        github: dict[str, IntegrationAdapter] = {"mock": MockGitHubAdapter()}
        if settings.github_token and settings.github_repo:
            github["real"] = RealGitHubAdapter(settings.github_token, settings.github_repo)
        candidates: dict[str, dict[str, IntegrationAdapter]] = {
            "github": github,
            "outlook": {"mock": MockOutlookAdapter()},
            "planner": {"mock": MockPlannerAdapter()},
            "sharepoint": {"mock": MockSharePointAdapter()},
            "teams": {"mock": MockTeamsAdapter()},
            "crm": {"mock": MockCRMAdapter()},
            "entra": {"mock": MockEntraAdapter()},
        }
        registry = build_registry(settings, candidates)

    # Knowledge grounding: real Foundry IQ when an endpoint is configured, else the offline fake
    # (also forced under FORCE_ALL_MOCK), mirroring the real-vs-mock selection above.
    knowledge: KnowledgePort = FakeKnowledgeProvider()
    if (
        not settings.force_all_mock
        and settings.knowledge_search_endpoint
        and settings.knowledge_base_name
    ):
        knowledge = FoundryIqKnowledgeProvider(
            endpoint=settings.knowledge_search_endpoint,
            knowledge_base_name=settings.knowledge_base_name,
            knowledge_source_name=settings.knowledge_source_name,
        )

    engine = make_engine(settings.db_url)
    init_db(engine)
    session_factory = make_session_factory(engine)
    audit_repo = SqlAuditRepository(session_factory)
    ledger = SqlVerdictLedger(session_factory)

    store = SqliteCheckpointStore.from_db_url(settings.db_url)
    store.setup()

    parser = request_parser if request_parser is not None else DeterministicRequestParser()

    graph = build_court_graph(
        intake=IntakeNode(parser, registry),
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
