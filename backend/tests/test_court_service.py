"""The service orchestrates submit/cast with ledger-backed idempotency and auto-resume."""

from __future__ import annotations

from app.agent.policy_rules.models import (
    MatchRules,
    RiskBands,
    RiskFactorRule,
    RulePack,
    VerdictOptionRules,
)
from app.config import Settings
from app.container import build_court_service
from app.domain import Change, ChangeStatus, ImpactEvidence, VerdictType
from app.ports.knowledge import KnowledgePort
from app.ports.registry import IntegrationRegistry

_PACK = RulePack(
    id="launch_slip",
    match=MatchRules(any_action_capability=["github.update_milestone_due"]),
    risk_factors=[
        RiskFactorRule(id="milestone_move", when_tag="schedule.milestone_move", weight=80)
    ],
    risk_bands=RiskBands(low=0, medium=30, high=60),
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
    return Settings(force_all_mock=True, db_url="sqlite:///:memory:", dry_run_default=True)


def test_submit_pauses_for_verdict_then_cast_completes_idempotently() -> None:
    service = build_court_service(
        _settings(), gatherers={"launch": _gatherer}, packs=[_PACK]
    )

    summary = service.submit_change("slip the launch from 2026-06-10 to 2026-06-17")
    assert summary.status == ChangeStatus.AWAITING_VERDICT.value
    assert summary.requires_approval is True
    assert "approve" in summary.verdict_options

    cast = service.cast_verdict(summary.thread_id, VerdictType.APPROVE)
    assert cast.verdict_recorded is True
    assert cast.execution_status == ChangeStatus.DONE.value
    assert cast.audit_id is not None

    # Casting the same verdict again is a no-op (same default idempotency key).
    again = service.cast_verdict(summary.thread_id, VerdictType.APPROVE)
    assert again.idempotent is True
    assert again.audit_id == cast.audit_id


def test_low_risk_change_auto_completes() -> None:
    # No rule packs -> no governing pack -> no approval required -> auto-resumed to DONE.
    service = build_court_service(_settings(), packs=[])
    summary = service.submit_change("slip the launch from 2026-06-10 to 2026-06-17")
    assert summary.status == ChangeStatus.DONE.value

    trial = service.get_trial(summary.thread_id)
    assert trial is not None
    assert trial.change.change_id == summary.change_id


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
        )
    )
    summary = service.submit_change("slip the launch from 2026-06-10 to 2026-06-17")
    assert summary.run_url is not None
    assert f"/runs/{summary.thread_id}" in summary.run_url

    cast = service.cast_verdict(summary.thread_id, VerdictType.APPROVE)
    assert cast.run_url is not None
    assert f"/runs/{summary.thread_id}" in cast.run_url


def test_run_url_is_none_when_run_page_disabled() -> None:
    service = build_court_service(_settings())  # no run_link_secret
    summary = service.submit_change("slip the launch from 2026-06-10 to 2026-06-17")
    assert summary.run_url is None

    cast = service.cast_verdict(summary.thread_id, VerdictType.APPROVE)
    assert cast.run_url is None
