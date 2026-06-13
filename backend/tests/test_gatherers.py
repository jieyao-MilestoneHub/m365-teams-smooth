"""The impact gatherers emit the expected evidence tags for each trial, from mock reads."""

from __future__ import annotations

from app.adapters.integrations.mock_github import MockGitHubAdapter
from app.adapters.integrations.mock_outlook import MockOutlookAdapter
from app.adapters.integrations.mock_planner import MockPlannerAdapter
from app.adapters.integrations.mock_teams import MockTeamsAdapter
from app.adapters.integrations.registry import ConfigIntegrationRegistry
from app.adapters.knowledge.local_corpus import LocalCorpusKnowledgeProvider
from app.agent.gatherers import gather_launch, gather_project_access, gather_sso_ga
from app.domain import Change, RequestedAction
from app.domain.errors import IntegrationError
from app.ports.integration import IntegrationAdapter, ReadQuery, ReadResult
from tests.conftest import build_mock_registry


class _ExplodingKnowledge:
    """A knowledge provider that fails every grounding call (e.g. an unreachable IQ endpoint)."""

    def ground(self, query: str, *, top_k: int = 3) -> list[object]:
        raise RuntimeError("knowledge base unreachable")


def test_gatherer_survives_an_unreachable_knowledge_provider() -> None:
    # Grounding is best-effort: a provider outage must cost the citations, not abort the trial.
    registry = build_mock_registry()
    errors: list[str] = []
    evidence = gather_launch(
        Change(change_id="c1", raw_request="move launch", subject="launch", due_by="2026-06-22"),
        registry,
        _ExplodingKnowledge(),  # type: ignore[arg-type]
        errors,
    )
    # The deterministic breach detection still stands; only its citations are absent.
    assert "schedule.contractual_breach_risk" in evidence.tags
    cf = next(i for i in evidence.items if i.kind == "counterfactual")
    assert cf.grounded == []
    assert any("knowledge grounding unavailable" in e for e in errors)


def test_launch_gatherer_tags_all_ripple_effects() -> None:
    registry = build_mock_registry()
    evidence = gather_launch(
        Change(change_id="c1", raw_request="slip", subject="launch", due_by="2026-06-17"),
        registry,
        LocalCorpusKnowledgeProvider(),
        [],
    )
    assert set(evidence.tags) == {
        "schedule.milestone_move",
        "schedule.calendar_conflict",
        "schedule.planner_shift",
        "comms.pending_announcement",
    }
    # A free-on-the-calendar date that breaches nothing: no derived contractual-breach tag.
    assert "schedule.contractual_breach_risk" not in evidence.tags


def test_launch_gatherer_derives_contractual_breach_across_systems() -> None:
    registry = build_mock_registry()
    evidence = gather_launch(
        # 2026-06-22 is free on the calendar but past the SLA (06-21), inside the freeze
        # (06-19..06-24), and inside the go-live buffer (06-26 - 5 days) — a conjunction breach.
        Change(change_id="c1", raw_request="move launch", subject="launch", due_by="2026-06-22"),
        registry,
        LocalCorpusKnowledgeProvider(),
        [],
    )
    assert "schedule.contractual_breach_risk" in evidence.tags
    cf = next(i for i in evidence.items if i.kind == "counterfactual")
    assert cf.severity == "high"
    reasons = cf.data["reasons"]
    assert isinstance(reasons, list) and len(reasons) >= 2  # the conjunction, not one system
    assert cf.grounded  # cited against the change-management policy


def test_sso_ga_gatherer_flags_review_after_due_date() -> None:
    registry = build_mock_registry()
    evidence = gather_sso_ga(
        Change(change_id="c1", raw_request="promise GA", subject="sso-ga", due_by="2026-06-17"),
        registry,
        LocalCorpusKnowledgeProvider(),
        [],
    )
    assert "github.blocking_issues_open" in evidence.tags
    assert "crm.renewal_at_risk" in evidence.tags
    assert "security.review_after_due_date" in evidence.tags  # review 2026-06-18 > 2026-06-17
    # the review evidence carries a grounded citation
    review = next(i for i in evidence.items if i.kind == "security_review")
    assert review.grounded


def test_project_access_gatherer_flags_ambiguity_scope_and_data() -> None:
    registry = build_mock_registry()
    change = Change(
        change_id="c1",
        raw_request="give vendor access",
        subject="project-access",
        requested_actions=[
            RequestedAction(
                system="sharepoint",
                capability_name="sharepoint.grant_folder_permission",
                params={"path": "/ProjectX", "principal": "v@example.com", "role": "write"},
            )
        ],
    )
    evidence = gather_project_access(change, registry, LocalCorpusKnowledgeProvider(), [])
    assert "access.ambiguous_duration" in evidence.tags  # no expiry in the request
    assert "access.overbroad_scope" in evidence.tags  # whole /ProjectX
    assert "data.customer_data_present" in evidence.tags  # /ProjectX holds customer data


class _FailingGitHubAdapter(MockGitHubAdapter):
    """A GitHub mock whose reads always raise, simulating an unavailable upstream."""

    def _read(self, query: ReadQuery) -> ReadResult:
        raise IntegrationError("github: upstream unavailable")


def test_launch_gatherer_degrades_when_one_read_fails() -> None:
    """A failing read is recorded and skipped; the other sources still produce evidence."""
    adapters: list[IntegrationAdapter] = [
        _FailingGitHubAdapter(),
        MockOutlookAdapter(),
        MockPlannerAdapter(),
        MockTeamsAdapter(),
    ]
    registry = ConfigIntegrationRegistry(adapters)
    errors: list[str] = []

    evidence = gather_launch(
        Change(change_id="c1", raw_request="slip", subject="launch", due_by="2026-06-17"),
        registry,
        LocalCorpusKnowledgeProvider(),
        errors,
    )

    # The GitHub read failed, so its tag is absent — but the run did not crash.
    assert "schedule.milestone_move" not in evidence.tags
    # The remaining systems still gathered evidence.
    assert "schedule.calendar_conflict" in evidence.tags
    assert "schedule.planner_shift" in evidence.tags
    assert "comms.pending_announcement" in evidence.tags
    # The failure is recorded for the audit trail.
    assert any("github.read_milestone" in e for e in errors)
