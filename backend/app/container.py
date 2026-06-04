"""Composition root: build the court service and its dependencies from settings.

This is the one place concrete adapters are chosen and wired. Gatherers, planners, and rule packs
are injected here; they are empty until Phase 3 fills them, at which point only this file changes.
"""

from __future__ import annotations

from datetime import date

from app.adapters.integrations.graph import GraphClient
from app.adapters.integrations.mock_crm import MockCRMAdapter
from app.adapters.integrations.mock_entra import MockEntraAdapter
from app.adapters.integrations.mock_github import MockGitHubAdapter
from app.adapters.integrations.mock_outlook import MockOutlookAdapter
from app.adapters.integrations.mock_planner import MockPlannerAdapter
from app.adapters.integrations.mock_sharepoint import MockSharePointAdapter
from app.adapters.integrations.mock_teams import MockTeamsAdapter
from app.adapters.integrations.real_github import RealGitHubAdapter
from app.adapters.integrations.real_outlook import RealOutlookAdapter
from app.adapters.integrations.real_sharepoint import RealSharePointAdapter
from app.adapters.integrations.registry import build_registry
from app.adapters.integrations.retry import RetryPolicy
from app.adapters.knowledge.fake_knowledge import FakeKnowledgeProvider
from app.adapters.knowledge.foundry_iq import FoundryIqKnowledgeProvider
from app.adapters.llm.azure_openai import AzureOpenAILLMProvider
from app.adapters.llm.fake_llm import FakeLLMProvider
from app.adapters.parsers.deterministic import DeterministicRequestParser
from app.adapters.parsers.llm_backed import LlmRequestParser
from app.adapters.persistence.checkpointer import SqliteCheckpointStore
from app.adapters.persistence.db import init_db, make_engine, make_session_factory
from app.adapters.persistence.repositories import (
    SqlApprovalLedger,
    SqlAuditRepository,
    SqlVerdictLedger,
)
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
from app.ports.llm import LLMProvider
from app.ports.registry import IntegrationRegistry
from app.ports.request_parser import RequestParser
from app.services.approver_directory import ApproverDirectory
from app.services.court_service import CourtService
from app.services.maintenance import MaintenanceService


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

    # Config-driven retry policy for the real-I/O adapters (mocks keep the disabled default).
    retry = RetryPolicy.from_settings(settings)

    if registry is None:
        github: dict[str, IntegrationAdapter] = {"mock": MockGitHubAdapter()}
        if settings.github_token and settings.github_repo:
            github["real"] = RealGitHubAdapter(
                settings.github_token, settings.github_repo, retry=retry
            )

        # Read-only real evidence over Microsoft Graph (Outlook calendar, SharePoint folders).
        # One shared app-only client; a real adapter is offered only when its target is configured.
        outlook: dict[str, IntegrationAdapter] = {"mock": MockOutlookAdapter()}
        sharepoint: dict[str, IntegrationAdapter] = {"mock": MockSharePointAdapter()}
        graph_ready = bool(
            not settings.force_all_mock
            and settings.graph_tenant_id
            and settings.graph_client_id
            and settings.graph_client_secret
        )
        if graph_ready:
            graph = GraphClient(
                settings.graph_tenant_id,
                settings.graph_client_id,
                settings.graph_client_secret,
            )
            if settings.outlook_calendar_upn:
                outlook["real"] = RealOutlookAdapter(
                    graph, settings.outlook_calendar_upn, retry=retry
                )
            if settings.sharepoint_site_id:
                sharepoint["real"] = RealSharePointAdapter(
                    graph, settings.sharepoint_site_id, retry=retry
                )

        candidates: dict[str, dict[str, IntegrationAdapter]] = {
            "github": github,
            "outlook": outlook,
            "planner": {"mock": MockPlannerAdapter()},
            "sharepoint": sharepoint,
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
            timeout=settings.http_timeout_seconds,
        )

    engine = make_engine(settings.db_url)
    init_db(engine)
    session_factory = make_session_factory(engine)
    audit_repo = SqlAuditRepository(session_factory)
    ledger = SqlVerdictLedger(session_factory)
    approvals = SqlApprovalLedger(session_factory)
    directory = ApproverDirectory.from_settings(settings)

    store = SqliteCheckpointStore.from_db_url(settings.db_url)
    store.setup()

    # Agentic parsing: real Azure OpenAI when configured, else the offline fake + deterministic.
    # (The LLM-backed parser always falls back to deterministic, keeping trials reproducible.)
    llm: LLMProvider = FakeLLMProvider()
    llm_is_real = bool(
        not settings.force_all_mock
        and settings.azure_openai_endpoint
        and settings.azure_openai_deployment
    )
    if llm_is_real:
        llm = AzureOpenAILLMProvider(
            endpoint=settings.azure_openai_endpoint,
            deployment=settings.azure_openai_deployment,
            api_version=settings.azure_openai_api_version,
            api_key=settings.llm_api_key,
            timeout=settings.llm_timeout_seconds,
            max_tokens=settings.llm_max_tokens,
        )

    # Anchor year-less natural dates ("June 17") to the current year at the composition root.
    today = date.today().isoformat()
    if request_parser is not None:
        parser: RequestParser = request_parser
    elif llm_is_real:
        parser = LlmRequestParser(
            llm, registry, fallback=DeterministicRequestParser(today=today), today=today
        )
    else:
        parser = DeterministicRequestParser(today=today)

    graph = build_court_graph(
        intake=IntakeNode(parser, registry),
        impact=ImpactNode(registry, knowledge, gatherers),
        options=OptionsNode(planners),
        policy=PolicyNode(packs, RulePackQuorumResolver()),
        execute=ExecuteNode(registry),
        audit=AuditNode(audit_repo),
        checkpointer=store.saver(),
    )
    runner = CourtRunner(graph, timeout_seconds=settings.graph_timeout_seconds)
    return CourtService(
        runner,
        audit_repo,
        ledger,
        registry=registry,
        approvals=approvals,
        directory=directory,
        dry_run_default=settings.dry_run_default,
        max_request_chars=settings.max_request_chars,
    )


def build_maintenance_service(settings: Settings) -> MaintenanceService:
    """Wire the retention maintenance service against the same database as the court."""
    engine = make_engine(settings.db_url)
    init_db(engine)
    session_factory = make_session_factory(engine)
    store = SqliteCheckpointStore.from_db_url(settings.db_url)
    store.setup()
    return MaintenanceService(
        store,
        SqlAuditRepository(session_factory),
        SqlVerdictLedger(session_factory),
    )
