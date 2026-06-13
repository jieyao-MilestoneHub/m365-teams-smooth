"""Approval notifications: pushed on send-for-approval and on the decision, never blocking."""

from __future__ import annotations

import logging

import httpx
import pytest

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

REQUESTER = Principal(
    oid="low-1", upn="lowpriv@agentleague.onmicrosoft.com", display_name="Robin Requester"
)
APPROVER = Principal(
    oid="joel-1", upn="joel@agentleague.onmicrosoft.com", display_name="Alex Approver"
)

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
    assert event["approver_upns"] == ["joel@agentleague.onmicrosoft.com"]  # delivery: real UPN
    assert event["note"] == "one more week"
    assert event["requester_upn"] == REQUESTER.display_name  # text label: the display name


def test_send_for_approval_warns_when_the_only_approver_is_the_requester(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Same-identity trap: the directory's only approver for the convened role is the requester,
    # so self-approval filtering leaves zero recipients. The send must warn with the reason, not
    # silently strand the trial in AWAITING_APPROVAL.
    notifier = FakeNotifier()
    settings = Settings(
        force_all_mock=True,
        db_url="sqlite:///:memory:",
        dry_run_default=True,
        approver_directory=f"eng_lead:{REQUESTER.upn}",
    )
    service = build_court_service(
        settings, gatherers={"launch": _gatherer}, packs=[_PACK], notifier=notifier
    )
    s = service.submit_change(_REQ, requester=REQUESTER)
    with caplog.at_level(logging.WARNING):
        service.send_for_approval(s.thread_id, actor=REQUESTER, note="ready")
    assert notifier.requested == []  # no one distinct to notify
    warning = next(r for r in caplog.records if r.getMessage() == "notify.no_recipients")
    assert "only to the requester" in getattr(warning, "reason", "")


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
    assert event["decider_upn"] == APPROVER.display_name


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
    assert result.execution_status == "done"
    assert len(notifier.decisions) == 1
    event = notifier.decisions[0]
    assert event["requester_upn"] == REQUESTER.upn
    assert event["approved"] is True
    assert event["decider_upn"] == APPROVER.display_name


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

    def acknowledged(self, **_: object) -> None:
        raise RuntimeError("graph down")


def test_requester_ack_closes_the_loop() -> None:
    # change → notify → ack: the requester's confirmation reaches the decider and is recorded.
    notifier = FakeNotifier()
    service = _service(notifier)
    s = service.submit_change(_REQ, requester=REQUESTER)
    service.send_for_approval(s.thread_id, actor=REQUESTER, note="ready")
    service.decide(s.thread_id, actor=APPROVER, approve=True)
    summary = service.acknowledge(s.thread_id, actor=REQUESTER)
    assert summary.acknowledged is True
    assert len(notifier.acks) == 1
    ack = notifier.acks[0]
    assert ack["requester_upn"] == REQUESTER.display_name
    assert APPROVER.upn in str(ack["approver_upns"])


def test_repeat_ack_is_a_noop() -> None:
    notifier = FakeNotifier()
    service = _service(notifier)
    s = service.submit_change(_REQ, requester=REQUESTER)
    service.send_for_approval(s.thread_id, actor=REQUESTER, note="ready")
    service.decide(s.thread_id, actor=APPROVER, approve=True)
    service.acknowledge(s.thread_id, actor=REQUESTER)
    again = service.acknowledge(s.thread_id, actor=REQUESTER)
    assert again.acknowledged is True
    assert len(notifier.acks) == 1  # no second push


def test_only_the_requester_may_acknowledge() -> None:
    from app.domain.errors import SeparationOfDutiesError

    service = _service(FakeNotifier())
    s = service.submit_change(_REQ, requester=REQUESTER)
    service.send_for_approval(s.thread_id, actor=REQUESTER, note="ready")
    service.decide(s.thread_id, actor=APPROVER, approve=True)
    try:
        service.acknowledge(s.thread_id, actor=APPROVER)
        raise AssertionError("expected the approver's ack to be refused")
    except SeparationOfDutiesError:
        pass


def test_ack_requires_a_concluded_trial() -> None:
    from app.domain.errors import InvalidRequestError

    service = _service(FakeNotifier())
    s = service.submit_change(_REQ, requester=REQUESTER)
    service.send_for_approval(s.thread_id, actor=REQUESTER, note="ready")
    try:
        service.acknowledge(s.thread_id, actor=REQUESTER)
        raise AssertionError("expected ack on a pending trial to be refused")
    except InvalidRequestError:
        pass


def test_ack_after_cast_verdict_notifies_the_caster() -> None:
    # The cast_verdict path records no APPROVE event — the ack must still reach the caster.
    notifier = FakeNotifier()
    service = _service(notifier)
    s = service.submit_change(_REQ, requester=REQUESTER)
    service.send_for_approval(s.thread_id, actor=REQUESTER, note="ready")
    service.cast_verdict(s.thread_id, VerdictType.APPROVE, principal=APPROVER)
    service.acknowledge(s.thread_id, actor=REQUESTER)
    assert len(notifier.acks) == 1
    assert APPROVER.upn in str(notifier.acks[0]["approver_upns"])


def _capturing_graph() -> tuple[GraphClient, list[dict[str, object]]]:
    """A GraphClient over a MockTransport that records each notification payload."""
    calls: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/oauth2/v2.0/token"):
            return httpx.Response(200, json={"access_token": "t", "expires_in": 3600})
        import json

        calls.append(json.loads(request.content))
        return httpx.Response(204)

    graph = GraphClient(
        "tenant", "client", "secret", client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    return graph, calls


def _system_default_text(payload: dict[str, object]) -> str:
    params = payload.get("templateParameters", [])
    assert isinstance(params, list)
    return next(str(p["value"]) for p in params if p["name"] == "systemDefaultText")


def test_approval_toast_keeps_the_note_despite_a_long_title() -> None:
    # The note is the requester's required justification — it must survive the 150-char cap even
    # behind a long UPN and a long title (regression: it used to trail the title and get cut off).
    graph, calls = _capturing_graph()
    notifier = TeamsActivityNotifier(graph, link_url="https://teams.microsoft.com")
    notifier.approval_requested(
        thread_id="t1",
        title="Slip the launch date from 2026-06-17 to 2026-06-24 across every dependent system",
        requester_upn="requester@agentleague.onmicrosoft.com",
        approver_upns=["approver@agentleague.onmicrosoft.com"],
        note="UNIQUE_NOTE_MARKER please approve, security review is complete",
    )
    text = _system_default_text(calls[0])
    assert "UNIQUE_NOTE_MARKER" in text


def test_decided_toast_keeps_the_outcome_note() -> None:
    graph, calls = _capturing_graph()
    notifier = TeamsActivityNotifier(graph, link_url="https://teams.microsoft.com")
    notifier.decided(
        thread_id="t1",
        title="Slip the launch date from 2026-06-17 to 2026-06-24 across every dependent system",
        requester_upn="requester@agentleague.onmicrosoft.com",
        approved=True,
        decider_upn="approver@agentleague.onmicrosoft.com",
        note="UNIQUE_OUTCOME_MARKER 4/8 step(s) applied",
    )
    assert "UNIQUE_OUTCOME_MARKER" in _system_default_text(calls[0])


def test_ack_event_does_not_disturb_quorum() -> None:
    from app.domain.approval import (
        ApprovalDecision,
        ApprovalEvent,
        QuorumState,
        evaluate_quorum,
    )
    from app.domain.enums import ApproverRole

    events = [
        ApprovalEvent(
            event_id="e1",
            thread_id="t",
            actor=APPROVER,
            decision=ApprovalDecision.APPROVE,
            role=ApproverRole.ENG_LEAD,
        ),
        ApprovalEvent(
            event_id="e2", thread_id="t", actor=REQUESTER, decision=ApprovalDecision.ACK
        ),
    ]
    decision = evaluate_quorum(events, [ApproverRole.ENG_LEAD], "all")
    assert decision.state is QuorumState.SATISFIED


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
    assert result.execution_status == "done"


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
    assert "please" in str(body["previewText"])  # the note leads the preview
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
