"""The MCP tools drive a full trial: submit → get_trial → send/decide or cast, all via the
server. Every mutating tool keys off the authenticated principal — see the impersonation note
below for how unit tests bind one."""

from __future__ import annotations

from typing import Any, cast

import pytest

import app.mcp.tools as tools_module
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
from app.mcp.server import build_mcp_server
from app.ports.knowledge import KnowledgePort
from app.ports.registry import IntegrationRegistry
from app.services.court_service import CourtService
from tests.conftest import ALL_ROLE_DIRECTORY, APPROVER, REQUESTER

# FastMCP.call_tool does not run the ASGI auth middleware, so the auth contextvar is never bound in
# unit tests; the correct seam is the tools module's ``current_principal`` reader, monkeypatched to
# impersonate each caller. The transport-level binding itself is covered in test_mcp_security.


def _impersonate(monkeypatch: pytest.MonkeyPatch, principal: Principal | None) -> None:
    monkeypatch.setattr(tools_module, "current_principal", lambda: principal)


@pytest.fixture
def mcp():  # type: ignore[no-untyped-def]
    service: CourtService = build_court_service(
        Settings(
            force_all_mock=True,
            db_url="sqlite:///:memory:",
            dry_run_default=True,
            approver_directory=ALL_ROLE_DIRECTORY,
        )
    )
    return build_mcp_server(service)


async def _call(mcp: Any, name: str, args: dict[str, Any]) -> dict[str, Any]:
    outcome = cast("tuple[Any, dict[str, Any]]", await mcp.call_tool(name, args))
    return outcome[1]


async def test_all_court_tools_registered(mcp: Any) -> None:
    names = {t.name for t in await mcp.list_tools()}
    assert {
        "submit_change",
        "get_status",
        "get_trial",
        "cast_verdict",
        "send_for_approval",
        "withdraw_change",
        "decide",
        "list_pending_approvals",
    } <= names


async def test_submit_without_run_mode_honors_dry_run_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The MCP submit_change must not force dry-run: omitting run_mode follows DRY_RUN_DEFAULT, so a
    # live deployment (DRY_RUN_DEFAULT=false) executes real writes. (The bot already honors this.)
    _impersonate(monkeypatch, REQUESTER)
    live = build_court_service(
        Settings(
            force_all_mock=True,
            db_url="sqlite:///:memory:",
            dry_run_default=False,
            approver_directory=ALL_ROLE_DIRECTORY,
        )
    )
    summary = await _call(
        build_mcp_server(live),
        "submit_change",
        {"raw_request": "promise Customer A SSO is GA by 2026-06-17"},
    )
    assert live._runner.state(summary["thread_id"]).get("run_mode") == "live"


async def test_get_trial_unknown_surfaces_typed_error(mcp: Any) -> None:
    from mcp.server.fastmcp.exceptions import ToolError

    with pytest.raises(ToolError) as excinfo:
        await _call(mcp, "get_trial", {"thread_id": "does-not-exist"})
    # The shared not_found mapping reaches the tool surface.
    assert "not_found" in str(excinfo.value)


async def test_submit_then_cast_via_tools(mcp: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    _impersonate(monkeypatch, REQUESTER)
    summary = await _call(
        mcp, "submit_change", {"raw_request": "promise Customer A SSO is GA by 2026-06-17"}
    )
    assert summary["status"] == "awaiting_requester_review"
    assert summary["unsafe"] is True
    thread_id = summary["thread_id"]

    trial = await _call(mcp, "get_trial", {"thread_id": thread_id})
    assert trial["options"]["kind"] == "safe_alternative"
    # The per-node reasoning trace rides along on the trial record.
    nodes = {e["node"] for e in trial["deliberation"]["entries"]}
    assert {"intake", "impact", "options", "policy"} <= nodes

    # An authorized approver (≠ the requester) casts the verdict and the run resumes.
    _impersonate(monkeypatch, APPROVER)
    result = await _call(
        mcp,
        "cast_verdict",
        {
            "thread_id": thread_id,
            "verdict_type": "accept_alternative",
            "selected_plan": "safe_alternative",
        },
    )
    assert result["verdict_recorded"] is True
    assert result["execution_status"] == "done"
    assert result["audit_id"]


async def test_unauthenticated_submit_and_cast_are_unauthorized(
    mcp: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcp.server.fastmcp.exceptions import ToolError

    _impersonate(monkeypatch, None)
    with pytest.raises(ToolError) as excinfo:
        await _call(
            mcp, "submit_change", {"raw_request": "promise Customer A SSO is GA by 2026-06-17"}
        )
    assert "unauthorized" in str(excinfo.value)
    with pytest.raises(ToolError) as excinfo:
        await _call(mcp, "cast_verdict", {"thread_id": "t", "verdict_type": "approve"})
    assert "unauthorized" in str(excinfo.value)


# --- identity-aware approval tools ---------------------------------------------------------------

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

_REQ = "slip the launch from 2026-06-10 to 2026-06-17"


def _gatherer(
    change: Change, registry: IntegrationRegistry, knowledge: KnowledgePort, errors: list[str]
) -> ImpactEvidence:
    return ImpactEvidence(tags=["schedule.milestone_move"])


@pytest.fixture
def approval_mcp():  # type: ignore[no-untyped-def]
    """An MCP server whose service routes approvals through a configured directory."""
    service: CourtService = build_court_service(
        Settings(
            force_all_mock=True,
            db_url="sqlite:///:memory:",
            dry_run_default=True,
            approver_directory=f"eng_lead:{APPROVER.upn}",
        ),
        gatherers={"launch": _gatherer},
        packs=[_PACK],
    )
    return build_mcp_server(service)


async def test_two_identity_approval_flow_via_tools(
    approval_mcp: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _impersonate(monkeypatch, REQUESTER)
    summary = await _call(approval_mcp, "submit_change", {"raw_request": _REQ})
    assert summary["status"] == "awaiting_requester_review"
    thread_id = summary["thread_id"]

    sent = await _call(
        approval_mcp, "send_for_approval", {"thread_id": thread_id, "note": "please review"}
    )
    assert sent["status"] == "awaiting_approval"

    _impersonate(monkeypatch, APPROVER)
    queue = await _call(approval_mcp, "list_pending_approvals", {})
    assert thread_id in {item["thread_id"] for item in queue["pending"]}

    decided = await _call(approval_mcp, "decide", {"thread_id": thread_id, "approve": True})
    assert decided["status"] == "done"


async def test_self_approval_is_rejected_via_tools(
    approval_mcp: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcp.server.fastmcp.exceptions import ToolError

    _impersonate(monkeypatch, REQUESTER)
    summary = await _call(approval_mcp, "submit_change", {"raw_request": _REQ})
    thread_id = summary["thread_id"]
    await _call(approval_mcp, "send_for_approval", {"thread_id": thread_id, "note": "review"})

    with pytest.raises(ToolError) as excinfo:
        await _call(approval_mcp, "decide", {"thread_id": thread_id, "approve": True})
    assert "separation_of_duties" in str(excinfo.value)


async def test_withdraw_via_tools(approval_mcp: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    _impersonate(monkeypatch, REQUESTER)
    summary = await _call(approval_mcp, "submit_change", {"raw_request": _REQ})
    withdrawn = await _call(
        approval_mcp, "withdraw_change", {"thread_id": summary["thread_id"]}
    )
    assert withdrawn["status"] == "withdrawn"


async def test_approval_tools_require_authentication(
    approval_mcp: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcp.server.fastmcp.exceptions import ToolError

    _impersonate(monkeypatch, None)
    with pytest.raises(ToolError) as excinfo:
        await _call(approval_mcp, "send_for_approval", {"thread_id": "t", "note": "n"})
    assert "unauthorized_approver" in str(excinfo.value)


async def test_submit_change_analyze_returns_the_evidence_and_never_executes(
    mcp: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _impersonate(monkeypatch, REQUESTER)
    summary = await _call(
        mcp,
        "submit_change",
        {"raw_request": "promise Customer A SSO is GA by 2026-06-17", "run_mode": "analyze"},
    )
    assert summary["status"] == "analyzed"
    trial = await _call(mcp, "get_trial", {"thread_id": summary["thread_id"]})
    assert trial["results"] == []
    assert trial["quorum"] is not None  # the would-be approvers travel with the record
