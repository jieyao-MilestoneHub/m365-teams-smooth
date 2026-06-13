"""The service orchestrates submit/cast with ledger-backed idempotency under identity gates."""

from __future__ import annotations

import pytest

from app.adapters.notifiers import FakeNotifier
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
from app.domain import ApproverRole, Change, ChangeStatus, ImpactEvidence, RunMode, VerdictType
from app.domain.errors import InvalidRequestError, UnauthorizedApproverError
from app.domain.principal import Principal
from app.ports.knowledge import KnowledgePort
from app.ports.registry import IntegrationRegistry
from app.services.court_service import CourtService
from tests.conftest import ALL_ROLE_DIRECTORY, APPROVER, REQUESTER

# The quorum rule makes the pack derive a required approver, so cast_verdict (which authorizes
# the caster against the trial's required roles) is exercisable; a no-approver trial routes
# through send_for_approval instead.
_PACK = RulePack(
    id="launch_slip",
    match=MatchRules(any_action_capability=["github.update_milestone_due"]),
    risk_factors=[
        RiskFactorRule(id="milestone_move", when_tag="schedule.milestone_move", weight=80)
    ],
    risk_bands=RiskBands(low=0, medium=30, high=60),
    quorum=QuorumRules(
        approvers=[ApproverRule(role=ApproverRole.ENG_LEAD, when_tag="schedule.milestone_move")]
    ),
    verdict_options=VerdictOptionRules(default=[VerdictType.APPROVE, VerdictType.REJECT]),
)


def _gatherer(
    change: Change,
    registry: IntegrationRegistry,
    knowledge: KnowledgePort,
    errors: list[str],
) -> ImpactEvidence:
    return ImpactEvidence(tags=["schedule.milestone_move"])


def _settings() -> Settings:
    return Settings(
        force_all_mock=True,
        db_url="sqlite:///:memory:",
        dry_run_default=True,
        approver_directory=ALL_ROLE_DIRECTORY,
    )


_REQ = "slip the launch from 2026-06-10 to 2026-06-17"


def test_submit_holds_for_review_then_cast_completes_idempotently() -> None:
    service = build_court_service(
        _settings(), gatherers={"launch": _gatherer}, packs=[_PACK]
    )

    summary = service.submit_change(_REQ, requester=REQUESTER)
    assert summary.status == ChangeStatus.AWAITING_REQUESTER_REVIEW.value
    assert summary.requires_approval is True
    assert "approve" in summary.verdict_options

    cast = service.cast_verdict(summary.thread_id, VerdictType.APPROVE, principal=APPROVER)
    assert cast.verdict_recorded is True
    assert cast.execution_status == ChangeStatus.DONE.value
    assert cast.audit_id is not None

    # Casting the same verdict again is a no-op (same default idempotency key).
    again = service.cast_verdict(summary.thread_id, VerdictType.APPROVE, principal=APPROVER)
    assert again.idempotent is True
    assert again.audit_id == cast.audit_id


def test_low_risk_change_executes_on_requester_send() -> None:
    # An approval-free court (no packs AND no policy floor): the requester's own confirmation
    # carries the authority, so sending executes without an approval round-trip.
    service = build_court_service(_settings(), packs=[], fallback_pack=None)
    summary = service.submit_change(_REQ, requester=REQUESTER)
    assert summary.status == ChangeStatus.AWAITING_REQUESTER_REVIEW.value

    sent = service.send_for_approval(summary.thread_id, actor=REQUESTER, note="confirming")
    assert sent.status == ChangeStatus.DONE.value

    trial = service.get_trial(summary.thread_id)
    assert trial is not None
    assert trial.change.change_id == summary.change_id


def test_submit_without_a_requester_is_rejected() -> None:
    # Identity is part of the boundary: an approval gate without a requester cannot separate
    # duties, so the identity-free submit path no longer exists.
    service = build_court_service(_settings(), packs=[])
    with pytest.raises(InvalidRequestError, match="authenticated requester"):
        service.submit_change(_REQ)


def test_cast_verdict_without_a_principal_is_unauthorized() -> None:
    service = build_court_service(_settings(), gatherers={"launch": _gatherer}, packs=[_PACK])
    summary = service.submit_change(_REQ, requester=REQUESTER)
    with pytest.raises(UnauthorizedApproverError, match="authentication is required"):
        service.cast_verdict(summary.thread_id, VerdictType.APPROVE)


def test_cast_verdict_with_an_unconfigured_directory_is_unauthorized() -> None:
    # With no APPROVER_DIRECTORY configured the wired directory resolves no roles, so no
    # principal can be authorized — a quorum-bearing trial cannot be resumed by anyone.
    service = build_court_service(
        Settings(force_all_mock=True, db_url="sqlite:///:memory:", dry_run_default=True),
        gatherers={"launch": _gatherer},
        packs=[_PACK],
    )
    summary = service.submit_change(_REQ, requester=REQUESTER)
    with pytest.raises(UnauthorizedApproverError, match="not an authorized approver"):
        service.cast_verdict(summary.thread_id, VerdictType.APPROVE, principal=APPROVER)


def test_run_url_surfaced_in_summary_and_cast_when_run_page_enabled() -> None:
    # With a run-page secret configured, both the summary and the cast result carry the signed
    # deep link so the agent can hand the user one place to inspect the full pipeline and audit.
    service = build_court_service(
        Settings(
            force_all_mock=True,
            db_url="sqlite:///:memory:",
            dry_run_default=True,
            run_link_secret="test-secret",
            public_base_url="https://court.example.com",
            approver_directory=ALL_ROLE_DIRECTORY,
        )
    )
    summary = service.submit_change(_REQ, requester=REQUESTER)
    assert summary.run_url is not None
    assert f"/runs/{summary.thread_id}" in summary.run_url

    cast = service.cast_verdict(summary.thread_id, VerdictType.APPROVE, principal=APPROVER)
    assert cast.run_url is not None
    assert f"/runs/{summary.thread_id}" in cast.run_url


def test_run_url_is_none_when_run_page_disabled() -> None:
    service = build_court_service(_settings())  # no run_link_secret
    summary = service.submit_change(_REQ, requester=REQUESTER)
    assert summary.run_url is None

    cast = service.cast_verdict(summary.thread_id, VerdictType.APPROVE, principal=APPROVER)
    assert cast.run_url is None


def test_ticket_url_surfaces_when_configured() -> None:
    # The change ticket / system of record link is surfaced on the summary and the cast result so
    # a surface (the Copilot agent) can link straight to it; None when unset.
    ticket = "https://github.com/owner/name/issues/440"
    service = build_court_service(
        Settings(
            force_all_mock=True,
            db_url="sqlite:///:memory:",
            dry_run_default=True,
            approver_directory=ALL_ROLE_DIRECTORY,
            evidence_ticket_url=ticket,
        ),
        gatherers={"launch": _gatherer},
        packs=[_PACK],
    )
    summary = service.submit_change(_REQ, requester=REQUESTER)
    assert summary.ticket_url == ticket

    cast = service.cast_verdict(summary.thread_id, VerdictType.APPROVE, principal=APPROVER)
    assert cast.ticket_url == ticket

    # Unset -> None.
    plain = build_court_service(_settings(), gatherers={"launch": _gatherer}, packs=[_PACK])
    assert plain.submit_change(_REQ, requester=REQUESTER).ticket_url is None

# --- analysis-only mode: the impact check that never executes ---


def _analyze_service() -> CourtService:
    return build_court_service(_settings(), gatherers={"launch": _gatherer}, packs=[_PACK])


def test_analysis_only_terminates_analyzed_even_when_high_risk() -> None:
    service = _analyze_service()
    summary = service.submit_change(_REQ, run_mode=RunMode.ANALYZE, requester=REQUESTER)
    assert summary.status == ChangeStatus.ANALYZED.value
    assert summary.requires_approval is True  # the would-be gate, reported but never engaged

    trial = service.get_trial(summary.thread_id)
    assert trial is not None
    assert trial.risk is not None and trial.options is not None and trial.quorum is not None
    assert trial.results == []  # nothing executed
    assert trial.verdict is None  # neither cast nor auto-approved


def test_analysis_only_low_risk_does_not_execute() -> None:
    # Without the analyze guard the approval-free path would execute on the requester's send.
    service = build_court_service(_settings(), packs=[], fallback_pack=None)
    summary = service.submit_change(_REQ, run_mode=RunMode.ANALYZE, requester=REQUESTER)
    assert summary.status == ChangeStatus.ANALYZED.value
    trial = service.get_trial(summary.thread_id)
    assert trial is not None
    assert trial.results == []
    assert trial.verdict is None


def test_analysis_only_writes_the_audit_record() -> None:
    service = _analyze_service()
    summary = service.submit_change(_REQ, run_mode=RunMode.ANALYZE, requester=REQUESTER)
    audit_id = str(service._runner.state(summary.thread_id).get("audit_id") or "")
    record = service.get_audit(audit_id)
    assert record is not None
    assert record.run_mode is RunMode.ANALYZE
    assert record.status is ChangeStatus.ANALYZED


def test_analysis_only_rejects_a_verdict() -> None:
    service = _analyze_service()
    summary = service.submit_change(_REQ, run_mode=RunMode.ANALYZE, requester=REQUESTER)
    with pytest.raises(InvalidRequestError):
        service.cast_verdict(summary.thread_id, VerdictType.APPROVE, principal=APPROVER)
    trial = service.get_trial(summary.thread_id)
    assert trial is not None and trial.results == []


def test_analysis_only_fires_the_analyzed_notification() -> None:
    # The webhook channel is how the packet reaches an existing ticket — exactly one event,
    # carrying the thread, the request title, and the requester for the record.
    service = _analyze_service()
    fake = FakeNotifier()
    service.attach_notifier(fake)
    summary = service.submit_change(_REQ, run_mode=RunMode.ANALYZE, requester=REQUESTER)
    assert summary.status == ChangeStatus.ANALYZED.value
    assert fake.analyzed_events == [
        {
            "thread_id": summary.thread_id,
            "title": _REQ[:80],
            "requester_upn": REQUESTER.upn,
        }
    ]


def test_normal_submit_fires_no_analyzed_notification() -> None:
    service = _analyze_service()
    fake = FakeNotifier()
    service.attach_notifier(fake)
    service.submit_change(_REQ, requester=REQUESTER)
    assert fake.analyzed_events == []


def test_analyzed_notification_failure_does_not_fail_submit() -> None:
    class _ExplodingAnalyzed(FakeNotifier):
        def analyzed(self, **_: object) -> None:
            raise RuntimeError("channel down")

    service = _analyze_service()
    service.attach_notifier(_ExplodingAnalyzed())
    summary = service.submit_change(_REQ, run_mode=RunMode.ANALYZE, requester=REQUESTER)
    assert summary.status == ChangeStatus.ANALYZED.value


def test_analysis_only_skips_the_requester_review_hold() -> None:
    settings = Settings(
        force_all_mock=True,
        db_url="sqlite:///:memory:",
        dry_run_default=True,
        approver_directory="eng_lead:joel@example.com",
    )
    service = build_court_service(settings, gatherers={"launch": _gatherer}, packs=[_PACK])
    requester = Principal(oid="o-1", upn="req@example.com", display_name="Robin")
    summary = service.submit_change(_REQ, run_mode=RunMode.ANALYZE, requester=requester)
    assert summary.status == ChangeStatus.ANALYZED.value  # not AWAITING_REQUESTER_REVIEW
    trial = service.get_trial(summary.thread_id)
    assert trial is not None
    assert trial.change.requester is not None  # stamped for the record
    with pytest.raises(InvalidRequestError):
        service.send_for_approval(summary.thread_id, actor=requester, note="please")
    with pytest.raises(InvalidRequestError):
        service.withdraw_change(summary.thread_id, actor=requester)
