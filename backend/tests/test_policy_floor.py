"""The policy floor: a change no pack governs is never waved through."""

from __future__ import annotations

from app.agent.nodes.policy import PolicyNode, RulePackQuorumResolver
from app.agent.policy_rules.packs import UNGOVERNED
from app.agent.state import CourtState, initial_state, serialize
from app.config import Settings
from app.container import build_court_service
from app.domain import Change, ChangeStatus, Quorum, RiskLevel, RiskResult, RunMode
from app.domain.enums import ApproverRole
from app.domain.principal import Principal
from tests.conftest import REQUESTER

MANAGER = Principal(oid="mgr-1", upn="manager@example.com", display_name="Mo Manager")

# An off-script request: the deterministic parser leaves it unclassified with no actions.
_REQ = "tidy up the old project channels before the audit"


def _floor_state(change: Change) -> CourtState:
    state = initial_state(
        thread_id="t1",
        change_id=change.change_id,
        raw_request=change.raw_request,
        source="test",
        run_mode=RunMode.DRY_RUN,
    )
    state["change"] = serialize(change)
    state["impact"] = {"items": [], "tags": []}
    return state


def test_ungoverned_fallback_convenes_the_manager_quorum() -> None:
    node = PolicyNode([], RulePackQuorumResolver(), fallback_pack=UNGOVERNED)
    result = node(_floor_state(Change(change_id="c1", raw_request=_REQ)))
    assert result["status"] == ChangeStatus.AWAITING_VERDICT.value
    risk = RiskResult.model_validate(result["risk"])
    assert risk.level is RiskLevel.MEDIUM
    assert risk.requires_approval is True
    assert [f.id for f in risk.factors] == ["ungoverned_change"]
    quorum = Quorum.model_validate(result["quorum"])
    assert [a.role for a in quorum.required_approvers] == [ApproverRole.MANAGER]


def test_no_fallback_keeps_the_approval_free_court() -> None:
    # The escape hatch is itself a contract: explicitly disabling the floor restores the
    # auto-proceed path for deliberately approval-free courts.
    node = PolicyNode([], RulePackQuorumResolver(), fallback_pack=None)
    result = node(_floor_state(Change(change_id="c1", raw_request=_REQ)))
    assert result["status"] == ChangeStatus.EXECUTING.value
    assert RiskResult.model_validate(result["risk"]).requires_approval is False


def test_off_script_change_waits_for_the_manager_end_to_end() -> None:
    settings = Settings(
        force_all_mock=True,
        db_url="sqlite:///:memory:",
        dry_run_default=True,
        approver_directory=f"manager:{MANAGER.upn}",
    )
    service = build_court_service(settings, packs=[])  # floor defaulted
    summary = service.submit_change(_REQ, requester=REQUESTER)
    assert summary.status == ChangeStatus.AWAITING_REQUESTER_REVIEW.value
    assert summary.requires_approval is True

    sent = service.send_for_approval(summary.thread_id, actor=REQUESTER, note="please review")
    assert sent.status == ChangeStatus.AWAITING_APPROVAL.value  # not DONE — the floor held

    pending = service.list_pending_approvals(MANAGER)
    assert [p.thread_id for p in pending] == [summary.thread_id]

    decided = service.decide(summary.thread_id, actor=MANAGER, approve=True, note="reviewed")
    assert decided.status == ChangeStatus.DONE.value


def test_novel_llm_subject_lands_on_the_floor_end_to_end() -> None:
    # G1 x G2 integration contract: a novel-subject parse (kept, with its actions) flows
    # intake -> impact -> options -> policy and waits for the manager — never a free pass.
    from app.adapters.parsers.deterministic import DeterministicRequestParser
    from app.adapters.parsers.llm_backed import LlmRequestParser
    from app.ports.llm import LLMProvider

    class _StubLLM(LLMProvider):
        def complete(self, prompt: str, *, system: str | None = None) -> str:
            return (
                '{"subject": "channel-archival", "actions": '
                '[{"system": "teams", "capability_name": "teams.post_message", '
                '"params": "{}"}]}'
            )

    settings = Settings(
        force_all_mock=True,
        db_url="sqlite:///:memory:",
        dry_run_default=True,
        approver_directory=f"manager:{MANAGER.upn}",
    )
    from app.adapters.integrations.mock_teams import MockTeamsAdapter
    from app.adapters.integrations.registry import build_registry  # composition mirrors container

    registry = build_registry(settings, {"teams": {"mock": MockTeamsAdapter()}})
    parser = LlmRequestParser(_StubLLM(), registry, DeterministicRequestParser())
    service = build_court_service(settings, request_parser=parser, registry=registry)

    summary = service.submit_change("archive the old project channels", requester=REQUESTER)
    assert summary.requires_approval is True
    sent = service.send_for_approval(summary.thread_id, actor=REQUESTER, note="cleanup")
    assert sent.status == ChangeStatus.AWAITING_APPROVAL.value
    trial = service.get_trial(summary.thread_id)
    assert trial is not None and trial.change.subject == "channel-archival"
