"""Composition root: build the court service and its dependencies from settings.

This is the one place concrete adapters are chosen and wired. Gatherers, planners, and rule packs
are injected here, so adding one touches only this file.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

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
from app.adapters.integrations.real_teams import RealTeamsAdapter
from app.adapters.integrations.registry import build_registry
from app.adapters.integrations.retry import RetryPolicy
from app.adapters.knowledge.foundry_iq import FoundryIqKnowledgeProvider
from app.adapters.knowledge.local_corpus import LocalCorpusKnowledgeProvider
from app.adapters.llm.azure_openai import AzureOpenAILLMProvider
from app.adapters.llm.fake_llm import FakeLLMProvider
from app.adapters.notifiers.teams_activity import TeamsActivityNotifier
from app.adapters.parsers.deterministic import DeterministicRequestParser
from app.adapters.parsers.llm_backed import LlmRequestParser
from app.adapters.persistence.checkpointer import SqliteCheckpointStore
from app.adapters.persistence.db import init_db, make_engine, make_session_factory
from app.adapters.persistence.repositories import (
    SqlApprovalLedger,
    SqlAuditRepository,
    SqlConversationStore,
    SqlPrecedentStore,
    SqlRunEventSink,
    SqlVerdictLedger,
)
from app.agent.agentic.gatherer import LlmEvidenceGatherer
from app.agent.agentic.planner import LlmPlanner
from app.agent.deliberate import Deliberator, LlmDeliberator, OfflineDeliberator
from app.agent.gatherers import GATHERERS
from app.agent.graph import build_court_graph
from app.agent.instrument import RunEventEmitter, set_run_event_emitter
from app.agent.nodes.audit import AuditNode
from app.agent.nodes.execute import ExecuteNode
from app.agent.nodes.impact import Gatherer, ImpactNode
from app.agent.nodes.intake import IntakeNode
from app.agent.nodes.options import OptionsNode, Planner
from app.agent.nodes.policy import PolicyNode, RulePackQuorumResolver
from app.agent.nodes.verify import VerifyNode
from app.agent.planners import PLANNERS
from app.agent.policy_rules.models import RulePack
from app.agent.policy_rules.packs import default_packs
from app.agent.runner import CourtRunner
from app.config import Settings
from app.domain.run_events import RunEventKind
from app.ports.conversation_store import ConversationStore
from app.ports.integration import IntegrationAdapter
from app.ports.knowledge import KnowledgePort
from app.ports.llm import LLMProvider
from app.ports.notifier import ApprovalNotifier
from app.ports.registry import IntegrationRegistry
from app.ports.request_parser import RequestParser
from app.ports.run_event_sink import RunEventSink
from app.services.approver_directory import ApproverDirectory
from app.services.court_service import CourtService
from app.services.maintenance import MaintenanceService


def build_teams_notifier(settings: Settings) -> ApprovalNotifier | None:
    """The Teams activity-feed notifier, when notifications are configured; else ``None``."""
    if (
        settings.notify_mode == "teams"
        and settings.graph_tenant_id
        and settings.graph_client_id
        and settings.graph_client_secret
    ):
        return TeamsActivityNotifier(
            GraphClient(
                settings.graph_tenant_id,
                settings.graph_client_id,
                settings.graph_client_secret,
            ),
            link_url=settings.notification_link_url(),
            teams_app_id=settings.notify_teams_app_id,
        )
    return None


def _run_event_emitter(sink: RunEventSink) -> RunEventEmitter:
    """Adapt the node wrapper's (thread_id, phase, name, payload) calls to the durable sink."""

    def emit(thread_id: str, phase: str, name: str, payload: dict[str, object]) -> None:
        kind = RunEventKind.NODE_STARTED if phase == "started" else RunEventKind.NODE_FINISHED
        data = dict(payload)
        status = str(data.pop("status", "") or "")
        sink.emit(thread_id, kind, name, status=status, payload=data)

    return emit


def build_conversation_store(settings: Settings) -> ConversationStore:
    """The conversation-reference store over the same database the court uses."""
    engine = make_engine(settings.db_url)
    init_db(engine)
    return SqlConversationStore(make_session_factory(engine))


def build_court_service(
    settings: Settings,
    *,
    gatherers: dict[str, Gatherer] | None = None,
    planners: dict[str, Planner] | None = None,
    packs: list[RulePack] | None = None,
    registry: IntegrationRegistry | None = None,
    request_parser: RequestParser | None = None,
    notifier: ApprovalNotifier | None = None,
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

        # Real evidence + contained writes over Microsoft Graph (Outlook calendar, SharePoint
        # folders, Teams activity feed). One shared app-only client; a real adapter is offered only
        # when its target is configured.
        outlook: dict[str, IntegrationAdapter] = {"mock": MockOutlookAdapter()}
        sharepoint: dict[str, IntegrationAdapter] = {"mock": MockSharePointAdapter()}
        teams: dict[str, IntegrationAdapter] = {"mock": MockTeamsAdapter()}
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
            if settings.teams_notify_recipient:
                teams["real"] = RealTeamsAdapter(
                    graph,
                    recipient_upn=settings.teams_notify_recipient,
                    link_url=settings.notification_link_url(),
                    teams_app_id=settings.notify_teams_app_id,
                    retry=retry,
                )

        candidates: dict[str, dict[str, IntegrationAdapter]] = {
            "github": github,
            "outlook": outlook,
            "planner": {"mock": MockPlannerAdapter()},
            "sharepoint": sharepoint,
            "teams": teams,
            "crm": {"mock": MockCRMAdapter()},
            "entra": {"mock": MockEntraAdapter()},
        }
        registry = build_registry(settings, candidates)

    # Knowledge grounding: real Foundry IQ when an endpoint is configured, else the offline corpus
    # provider (also forced under FORCE_ALL_MOCK), mirroring the real-vs-mock selection above.
    knowledge: KnowledgePort = LocalCorpusKnowledgeProvider(
        corpus_dir=Path(settings.knowledge_corpus_dir) if settings.knowledge_corpus_dir else None
    )
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
            reasoning_effort=settings.knowledge_reasoning_effort,
        )

    engine = make_engine(settings.db_url)
    init_db(engine)
    session_factory = make_session_factory(engine)
    audit_repo = SqlAuditRepository(session_factory)
    ledger = SqlVerdictLedger(session_factory)
    approvals = SqlApprovalLedger(session_factory)
    directory = ApproverDirectory.from_settings(settings)
    memory = SqlPrecedentStore(session_factory)

    # Durable per-node/per-step progress for the run view. The node emitter is a process-wide
    # hook (mirroring the metrics duration hook): set once here, pointing at the same database
    # the service reads, so a concurrent poll sees events while the graph is still running.
    run_events = SqlRunEventSink(session_factory)
    set_run_event_emitter(_run_event_emitter(run_events))

    # Approval notifications: Teams activity feed when configured, else none (workflow unchanged).
    if notifier is None:
        notifier = build_teams_notifier(settings)

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

    # Agentic roles engage with a real LLM: the Prosecutor selects additional validated reads on
    # top of each subject's deterministic gatherer, and the Defender drafts each plan within the
    # deterministic baseline's kind (refusal authority stays deterministic). Offline/mocked runs
    # stay fully deterministic.
    if llm_is_real:
        gatherers = {
            subject: LlmEvidenceGatherer(
                llm, fallback=gatherer, max_reads=settings.max_agentic_reads, memory=memory
            )
            for subject, gatherer in gatherers.items()
        }
        planners = {
            subject: LlmPlanner(llm, registry, fallback=planner, memory=memory)
            for subject, planner in planners.items()
        }

    # Deliberation reasoning is captured by the LLM-backed deliberator exactly when the Prosecutor
    # and Defender are LLM-backed, so reused role prose is genuinely model-sourced; offline runs
    # record an honestly-labeled factual stub per node.
    deliberator: Deliberator = LlmDeliberator(llm) if llm_is_real else OfflineDeliberator()

    graph = build_court_graph(
        intake=IntakeNode(parser, registry, deliberator),
        impact=ImpactNode(registry, knowledge, gatherers, deliberator),
        options=OptionsNode(planners, deliberator),
        policy=PolicyNode(packs, RulePackQuorumResolver(), deliberator),
        execute=ExecuteNode(registry, sink=run_events),
        verify=VerifyNode(deliberator),
        audit=AuditNode(audit_repo, memory=memory),
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
        notifier=notifier,
        run_events=run_events,
        run_link_secret=settings.run_link_secret,
        public_base_url=settings.public_base_url,
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
        approvals=SqlApprovalLedger(session_factory),
    )
