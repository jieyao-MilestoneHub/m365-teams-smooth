"""Approval notifications: pushed on send-for-approval and on the decision, never blocking."""

from __future__ import annotations

import httpx

from app.adapters.integrations.graph import GraphClient
from app.adapters.notifiers import FakeNotifier, TeamsActivityNotifier
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
from app.domain import Change, ImpactEvidence, VerdictType
from app.domain.enums import ApproverRole
from app.domain.principal import Principal
from app.ports.knowledge import KnowledgePort
from app.ports.notifier import ApprovalNotifier
from app.ports.registry import IntegrationRegistry
from app.services.court_service import CourtService

REQUESTER = Principal(oid="low-1", upn="lowpriv@agentleague.onmicrosoft.com")
APPROVER = Principal(oid="joel-1", upn="joel@agentleague.onmicrosoft.com")

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


def _gatherer(
    change: Change, registry: IntegrationRegistry, knowledge: KnowledgePort, errors: list[str]
) -> ImpactEvidence:
    return ImpactEvidence(tags=["schedule.milestone_move"])


def _service(notifier: ApprovalNotifier) -> CourtService:
    settings = Settings(
        force_all_mock=True,
        db_url="sqlite:///:memory:",
        dry_run_default=True,
        approver_directory="eng_lead:joel@agentleague.onmicrosoft.com",
    )
    return build_court_service(
        settings, gatherers={"launch": _gatherer}, packs=[_PACK], notifier=notifier
    )


_REQ = "slip the launch from 2026-06-10 to 2026-06-17"


def test_send_for_approval_notifies_the_approvers() -> None:
    notifier = FakeNotifier()
    service = _service(notifier)
    s = service.submit_change(_REQ, requester=REQUESTER)
    service.send_for_approval(s.thread_id, actor=REQUESTER, note="one more week")
    assert len(notifier.requested) == 1
    event = notifier.requested[0]
    assert event["thread_id"] == s.thread_id
    assert event["approver_upns"] == ["joel@agentleague.onmicrosoft.com"]
    assert event["note"] == "one more week"
    assert event["requester_upn"] == REQUESTER.upn


def test_decide_notifies_the_requester_with_the_outcome() -> None:
    notifier = FakeNotifier()
    service = _service(notifier)
    s = service.submit_change(_REQ, requester=REQUESTER)
    service.send_for_approval(s.thread_id, actor=REQUESTER, note="ready")
    service.decide(s.thread_id, actor=APPROVER, approve=True)
    assert len(notifier.decisions) == 1
    event = notifier.decisions[0]
    assert event["requester_upn"] == REQUESTER.upn
    assert event["approved"] is True
    assert event["decider_upn"] == APPROVER.upn


def test_decided_note_carries_the_execution_outcome() -> None:
    # The toast must say what happened — a dry-run trial reports predicted steps.
    notifier = FakeNotifier()
    service = _service(notifier)
    s = service.submit_change(_REQ, requester=REQUESTER)
    service.send_for_approval(s.thread_id, actor=REQUESTER, note="ready")
    service.decide(s.thread_id, actor=APPROVER, approve=True, note="go")
    note = str(notifier.decisions[0]["note"])
    assert "go" in note
    assert "predicted (dry-run)" in note


def test_decided_note_reports_applied_steps_in_live_mode() -> None:
    from app.domain import RunMode

    notifier = FakeNotifier()
    service = _service(notifier)
    s = service.submit_change(_REQ, run_mode=RunMode.LIVE, requester=REQUESTER)
    service.send_for_approval(s.thread_id, actor=REQUESTER, note="ready")
    service.decide(s.thread_id, actor=APPROVER, approve=True)
    assert "step(s) applied" in str(notifier.decisions[0]["note"])


def test_cast_verdict_notifies_the_requester() -> None:
    # The legacy verdict gate is terminal too — the requester must hear the outcome from it
    # exactly as they would from decide().
    notifier = FakeNotifier()
    service = _service(notifier)
    s = service.submit_change(_REQ, requester=REQUESTER)
    service.send_for_approval(s.thread_id, actor=REQUESTER, note="ready")
    result = service.cast_verdict(s.thread_id, VerdictType.APPROVE, principal=APPROVER)
    assert result.status == "done"
    assert len(notifier.decisions) == 1
    event = notifier.decisions[0]
    assert event["requester_upn"] == REQUESTER.upn
    assert event["approved"] is True
    assert event["decider_upn"] == APPROVER.upn


def test_duplicate_cast_verdict_does_not_renotify() -> None:
    notifier = FakeNotifier()
    service = _service(notifier)
    s = service.submit_change(_REQ, requester=REQUESTER)
    service.send_for_approval(s.thread_id, actor=REQUESTER, note="ready")
    first = service.cast_verdict(s.thread_id, VerdictType.APPROVE, principal=APPROVER)
    replay = service.cast_verdict(s.thread_id, VerdictType.APPROVE, principal=APPROVER)
    assert replay.idempotent is True
    assert replay.audit_id == first.audit_id
    assert len(notifier.decisions) == 1  # the replay must not push a second toast


class _ExplodingNotifier(ApprovalNotifier):
    def approval_requested(self, **_: object) -> None:
        raise RuntimeError("graph down")

    def decided(self, **_: object) -> None:
        raise RuntimeError("graph down")


def test_notifier_failure_never_blocks_the_workflow() -> None:
    service = _service(_ExplodingNotifier())
    s = service.submit_change(_REQ, requester=REQUESTER)
    summary = service.send_for_approval(s.thread_id, actor=REQUESTER, note="ready")
    assert summary.status == "awaiting_approval"
    result = service.decide(s.thread_id, actor=APPROVER, approve=True)
    assert result.status == "done"


def test_notifier_failure_never_blocks_cast_verdict() -> None:
    service = _service(_ExplodingNotifier())
    s = service.submit_change(_REQ, requester=REQUESTER)
    service.send_for_approval(s.thread_id, actor=REQUESTER, note="ready")
    result = service.cast_verdict(s.thread_id, VerdictType.APPROVE, principal=APPROVER)
    assert result.status == "done"


def test_graph_error_body_is_surfaced() -> None:
    # The status line alone hides the actionable reason; the raised error must carry the body.
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/oauth2/v2.0/token"):
            return httpx.Response(200, json={"access_token": "t", "expires_in": 3600})
        return httpx.Response(
            400, json={"error": {"code": "BadRequest", "message": "template mismatch"}}
        )

    graph = GraphClient(
        "tenant", "client", "secret", client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    notifier = TeamsActivityNotifier(graph, link_url="https://teams.microsoft.com")
    try:
        notifier.decided(
            thread_id="t1",
            title="slip",
            requester_upn="lowpriv@x",
            approved=True,
            decider_upn="a@x",
            note="",
        )
        raise AssertionError("expected the Graph 400 to raise")
    except RuntimeError as err:
        assert "template mismatch" in str(err)


def test_teams_activity_notifier_posts_per_approver() -> None:
    # Stub the Graph transport: capture token + notification posts, assert the payload shape.
    calls: list[tuple[str, dict[str, object]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/oauth2/v2.0/token"):
            return httpx.Response(200, json={"access_token": "t", "expires_in": 3600})
        import json

        calls.append((request.url.path, json.loads(request.content)))
        return httpx.Response(204)

    graph = GraphClient(
        "tenant", "client", "secret", client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    notifier = TeamsActivityNotifier(graph, link_url="https://teams.microsoft.com")
    notifier.approval_requested(
        thread_id="t1",
        title="slip the launch",
        requester_upn="lowpriv@x",
        approver_upns=["a@x", "b@x"],
        note="please",
    )
    assert [path for path, _ in calls] == [
        "/v1.0/users/a@x/teamwork/sendActivityNotification",
        "/v1.0/users/b@x/teamwork/sendActivityNotification",
    ]
    body = calls[0][1]
    assert body["activityType"] == "systemDefault"
    assert "slip the launch" in str(body["previewText"])
    params = body["templateParameters"]
    assert isinstance(params, list)
    assert any(p["name"] == "systemDefaultText" for p in params)
    chain_id = body["chainId"]
    assert isinstance(chain_id, int) and 0 < chain_id < 2**63
    assert calls[1][1]["chainId"] == chain_id  # same trial -> same chain, later events override

    # The decision notification chains onto the same trial's toast.
    notifier.decided(
        thread_id="t1",
        title="slip the launch",
        requester_upn="lowpriv@x",
        approved=True,
        decider_upn="a@x",
        note="",
    )
    assert calls[-1][1]["chainId"] == chain_id
    # A different trial gets its own chain.
    notifier.decided(
        thread_id="t2",
        title="another change",
        requester_upn="lowpriv@x",
        approved=False,
        decider_upn="a@x",
        note="no",
    )
    assert calls[-1][1]["chainId"] != chain_id
