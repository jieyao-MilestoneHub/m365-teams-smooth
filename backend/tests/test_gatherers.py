"""The impact gatherers emit the expected evidence tags for each trial, from mock reads."""

from __future__ import annotations

from app.adapters.knowledge.fake_knowledge import FakeKnowledgeProvider
from app.agent.gatherers import gather_launch, gather_project_access, gather_sso_ga
from app.domain import Change, RequestedAction
from tests.conftest import build_mock_registry


def test_launch_gatherer_tags_all_ripple_effects() -> None:
    registry = build_mock_registry()
    evidence = gather_launch(
        Change(change_id="c1", raw_request="slip", subject="launch", due_by="2026-06-17"),
        registry,
        FakeKnowledgeProvider(),
    )
    assert set(evidence.tags) == {
        "schedule.milestone_move",
        "schedule.calendar_conflict",
        "schedule.planner_shift",
        "comms.pending_announcement",
    }


def test_sso_ga_gatherer_flags_review_after_due_date() -> None:
    registry = build_mock_registry()
    evidence = gather_sso_ga(
        Change(change_id="c1", raw_request="promise GA", subject="sso-ga", due_by="2026-06-17"),
        registry,
        FakeKnowledgeProvider(),
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
    evidence = gather_project_access(change, registry, FakeKnowledgeProvider())
    assert "access.ambiguous_duration" in evidence.tags  # no expiry in the request
    assert "access.overbroad_scope" in evidence.tags  # whole /ProjectX
    assert "data.customer_data_present" in evidence.tags  # /ProjectX holds customer data
