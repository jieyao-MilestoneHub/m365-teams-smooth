"""Evidence webhook notifier: one bounded POST per approval event, best-effort end to end."""

from __future__ import annotations

import json
from typing import cast

import httpx
import pytest
import respx

from app.adapters.notifiers.evidence_webhook import EvidenceWebhookNotifier
from app.agent.policy_rules.models import (
    ApproverRule,
    MatchRules,
    QuorumRules,
    RiskBands,
    RiskFactorRule,
    RulePack,
    VerdictOptionRules,
)
from app.config import Settings
from app.container import build_court_service
from app.domain import (
    Change,
    ImpactEvidence,
    TrialRecord,
    VerdictType,
)
from app.domain.capability import CapabilityRef
from app.domain.enums import ApproverRole, PlanKind, RiskLevel, StepStatus
from app.domain.impact import EvidenceItem, GroundedFact
from app.domain.plan import ExecutionPlan, ExecutionStep, StepResult
from app.domain.principal import Principal
from app.domain.quorum import Approver, Quorum
from app.domain.risk import RiskFactor, RiskResult
from app.ports.knowledge import KnowledgePort
from app.ports.registry import IntegrationRegistry

_URL = "https://tickets.example.com/hooks/change-court"


def _trial() -> TrialRecord:
    return TrialRecord(
        change=Change(
            change_id="c-1",
            raw_request="slip the launch to 2026-06-22",
            subject="launch",
            requester=Principal(oid="o-1", upn="req@example.com", display_name="Robin"),
        ),
        impact=ImpactEvidence(
            tags=["schedule.milestone_move"],
            items=[
                EvidenceItem(
                    system="crm",
                    kind="contract",
                    summary="launch-readiness SLA ends 2026-06-21",
                    severity="high",
                    grounded=[GroundedFact(claim="LR-3", source_id="crm", citation="LR-3")],
                )
            ],
        ),
        options=ExecutionPlan(
            kind=PlanKind.FEASIBLE,
            rationale="single milestone move",
            steps=[
                ExecutionStep(
                    step_id="s1",
                    capability=CapabilityRef(system="github", name="update_milestone_due"),
                )
            ],
        ),
        risk=RiskResult(
            level=RiskLevel.HIGH,
            score=80,
            requires_approval=True,
            factors=[
                RiskFactor(
                    id="m",
                    label="milestone move",
                    weight=80,
                    evidence_tag="schedule.milestone_move",
                    grounded_citations=["GOV-1"],
                )
            ],
        ),
        quorum=Quorum(
            required_approvers=[Approver(role=ApproverRole.ENG_LEAD)],
            policy="all",
        ),
        results=[StepResult(step_id="s1", status=StepStatus.DRY_RUN)],
    )


def _notifier(token: str = "", trial: TrialRecord | None = None) -> EvidenceWebhookNotifier:
    return EvidenceWebhookNotifier(
        url=_URL,
        trial_reader=lambda thread_id: trial,
        run_link=lambda thread_id: f"https://court.example.com/runs/{thread_id}?t=sig",
        token=token,
    )


@respx.mock
def test_approval_requested_posts_the_full_packet() -> None:
    route = respx.post(_URL).mock(return_value=httpx.Response(200))
    _notifier(trial=_trial()).approval_requested(
        thread_id="t-1",
        title="launch",
        requester_upn="Robin",
        approver_upns=["lead@example.com"],
        note="one more week",
    )
    assert route.call_count == 1
    payload = json.loads(route.calls[0].request.content)
    assert payload["event"] == "approval_requested"
    assert payload["thread_id"] == "t-1"
    assert payload["approvers"] == ["lead@example.com"]
    assert payload["note"] == "one more week"
    assert payload["change"]["raw_request"] == "slip the launch to 2026-06-22"
    assert payload["risk"]["level"] == "high"
    assert payload["risk"]["factors"][0]["citations"] == ["GOV-1"]
    assert payload["impact"]["tags"] == ["schedule.milestone_move"]
    assert payload["impact"]["items"][0]["citations"] == ["LR-3"]
    assert payload["plan"]["steps"] == [
        {"step_id": "s1", "system": "github", "capability": "update_milestone_due"}
    ]
    assert payload["quorum"] == {"policy": "all", "required_roles": ["eng_lead"]}
    assert payload["run_url"] == "https://court.example.com/runs/t-1?t=sig"


@respx.mock
def test_decided_includes_the_decision_and_results() -> None:
    route = respx.post(_URL).mock(return_value=httpx.Response(200))
    _notifier(trial=_trial()).decided(
        thread_id="t-2",
        title="launch",
        requester_upn="Robin",
        approved=True,
        decider_upn="lead@example.com",
        note="ship it",
    )
    payload = json.loads(route.calls[0].request.content)
    assert payload["event"] == "decided"
    assert payload["approved"] is True
    assert payload["decider"] == "lead@example.com"
    assert payload["results"] == [
        {"step_id": "s1", "status": "dry_run", "error": None, "resource_url": None}
    ]


@respx.mock
def test_acknowledged_posts_the_approvers() -> None:
    route = respx.post(_URL).mock(return_value=httpx.Response(200))
    _notifier(trial=_trial()).acknowledged(
        thread_id="t-3",
        title="launch",
        requester_upn="Robin",
        approver_upns=["lead@example.com"],
    )
    payload = json.loads(route.calls[0].request.content)
    assert payload["event"] == "acknowledged"
    assert payload["approvers"] == ["lead@example.com"]


@respx.mock
def test_bearer_token_sent_only_when_configured() -> None:
    route = respx.post(_URL).mock(return_value=httpx.Response(200))
    _notifier(token="s3cret", trial=_trial()).acknowledged(
        thread_id="t-4", title="launch", requester_upn="Robin", approver_upns=[]
    )
    _notifier(trial=_trial()).acknowledged(
        thread_id="t-4", title="launch", requester_upn="Robin", approver_upns=[]
    )
    assert route.calls[0].request.headers["authorization"] == "Bearer s3cret"
    assert "authorization" not in route.calls[1].request.headers


@respx.mock
def test_non_2xx_raises_per_the_port_contract() -> None:
    respx.post(_URL).mock(return_value=httpx.Response(500))
    with pytest.raises(httpx.HTTPStatusError):
        _notifier(trial=_trial()).acknowledged(
            thread_id="t-5", title="launch", requester_upn="Robin", approver_upns=[]
        )


@respx.mock
def test_unreadable_trial_still_posts_the_event_fields() -> None:
    route = respx.post(_URL).mock(return_value=httpx.Response(200))
    _notifier(trial=None).approval_requested(
        thread_id="t-6", title="launch", requester_upn="Robin", approver_upns=[], note=""
    )
    payload = json.loads(route.calls[0].request.content)
    assert payload["event"] == "approval_requested"
    assert "change" not in payload


def test_channel_is_off_when_no_url_is_configured() -> None:
    from app.container import build_evidence_webhook_notifier

    settings = Settings(force_all_mock=True, db_url="sqlite:///:memory:")
    assert settings.evidence_webhook_url == ""
    assert settings.evidence_webhook_token == ""
    notifier = build_evidence_webhook_notifier(
        settings, trial_reader=lambda thread_id: None, run_link=lambda thread_id: None
    )
    assert notifier is None


# --- end-to-end: a failing webhook never blocks the approval workflow ---

_PACK = RulePack(
    id="launch_slip",
    match=MatchRules(any_action_capability=["github.update_milestone_due"]),
    risk_factors=[RiskFactorRule(id="m", when_tag="schedule.milestone_move", weight=80)],
    risk_bands=RiskBands(low=0, medium=30, high=60),
    quorum=QuorumRules(
        approvers=[ApproverRule(role=ApproverRole.ENG_LEAD, when_tag="schedule.milestone_move")],
        policy="all",
    ),
    verdict_options=VerdictOptionRules(default=[VerdictType.APPROVE, VerdictType.REJECT]),
)

_REQUESTER = Principal(oid="low-1", upn="req@example.com", display_name="Robin Requester")


def _gatherer(
    change: Change, registry: IntegrationRegistry, knowledge: KnowledgePort, errors: list[str]
) -> ImpactEvidence:
    return ImpactEvidence(tags=["schedule.milestone_move"])


@respx.mock
def test_webhook_failure_does_not_fail_send_for_approval() -> None:
    route = respx.post(_URL).mock(return_value=httpx.Response(500))
    settings = Settings(
        force_all_mock=True,
        db_url="sqlite:///:memory:",
        dry_run_default=True,
        approver_directory="eng_lead:joel@example.com",
        evidence_webhook_url=_URL,
    )
    service = build_court_service(settings, gatherers={"launch": _gatherer}, packs=[_PACK])
    summary = service.submit_change(
        "slip the launch from 2026-06-10 to 2026-06-17", requester=_REQUESTER
    )
    service.send_for_approval(summary.thread_id, actor=_REQUESTER, note="one more week")
    assert route.call_count == 1  # the channel fired, failed, and was contained
    payload = json.loads(route.calls[0].request.content)
    assert payload["event"] == "approval_requested"
    assert cast(dict[str, object], payload["risk"])["requires_approval"] is True
