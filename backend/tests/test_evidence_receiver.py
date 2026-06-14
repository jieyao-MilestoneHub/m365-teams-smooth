"""The evidence receiver turns one webhook packet into one ticket comment, best-effort."""

from __future__ import annotations

import importlib
import sys

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

_PACKET: dict[str, object] = {
    "event": "approval_requested",
    "thread_id": "t-1",
    "note": "one more week",
    "change": {"raw_request": "move the launch rehearsal to 2026-06-22"},
    "risk": {
        "level": "high",
        "requires_approval": True,
        # Mirrors production: the policy node stamps the same trial-wide citation list onto every
        # fired factor, so the renderer must dedupe and group them rather than repeat per line.
        "factors": [
            {
                "id": "m",
                "label": "milestone_move",
                "severity": "medium",
                "evidence_tag": "schedule.milestone_move",
                "citations": [
                    "Release & Change Management Policy — Schedule changes are controlled changes",
                    "Release & Change Management Policy — Coordinated downstream updates",
                    "Meeting & Event Scheduling Guidelines — Rescheduling a routine meeting",
                ],
            },
            {
                "id": "c",
                "label": "contractual_breach_risk",
                "severity": "high",
                "evidence_tag": "schedule.contractual_breach_risk",
                "citations": [
                    "Release & Change Management Policy — Schedule changes are controlled changes",
                    "Release & Change Management Policy — Coordinated downstream updates",
                    "Meeting & Event Scheduling Guidelines — Rescheduling a routine meeting",
                ],
            },
        ],
    },
    "impact": {
        "tags": ["schedule.milestone_move"],
        # The gatherer's own grouping of its findings; the comment shows these as the risk drivers.
        "drivers": [
            "Contract cut-off breach",
            "Release-freeze window",
            "Customer go-live buffer",
            "Downstream schedule updates",
        ],
        "items": [
            {
                "system": "crm",
                "kind": "contract",
                "summary": "launch-readiness SLA ends 2026-06-21",
                "severity": "high",
                "citations": ["LR-3"],
            }
        ],
    },
    "plan": {
        "kind": "safe_alternative",
        "rationale": "move to 2026-06-18 instead",
        "supersedes_request": True,
        "steps": [{"step_id": "s1", "system": "github", "capability": "update_milestone_due"}],
    },
    "quorum": {"policy": "any", "required_roles": ["eng_lead"]},
    "run_url": "https://court.example.com/runs/t-1?t=sig",
}


def _load_app(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("GITHUB_TOKEN", "gh-token")
    monkeypatch.setenv("GITHUB_REPO", "owner/name")
    monkeypatch.setenv("EVIDENCE_ISSUE", "123")
    sys.modules.pop("scripts.evidence_receiver", None)
    return importlib.import_module("scripts.evidence_receiver")


@respx.mock
def test_one_post_becomes_one_issue_comment(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_app(monkeypatch)
    route = respx.post("https://api.github.com/repos/owner/name/issues/123/comments").mock(
        return_value=httpx.Response(201)
    )
    result = TestClient(module.app).post("/evidence", json=_PACKET)
    assert result.status_code == 200
    assert result.json() == {"status": "posted"}
    assert route.call_count == 1
    request = route.calls[0].request
    assert request.headers["authorization"] == "Bearer gh-token"
    body = str(request.content.decode())
    assert "Change Court — Approval requested" in body
    assert "move the launch rehearsal to 2026-06-22" in body
    # The "why" lines are the gatherer's reader-facing drivers, with no inline weights.
    assert "**Why this is high risk**" in body
    assert "- Contract cut-off breach" in body
    assert "- Release-freeze window" in body
    assert "- Customer go-live buffer" in body
    assert "- Downstream schedule updates" in body
    assert "+40" not in body and "+50" not in body and "(+" not in body
    # The shared citations are deduped once and grouped under each policy, not repeated per factor.
    assert "**Policy basis**" in body
    assert body.count("Release & Change Management Policy") == 1
    assert "- Release & Change Management Policy" in body
    assert "  - Schedule changes are controlled changes" in body
    assert "  - Coordinated downstream updates" in body
    assert "- Meeting & Event Scheduling Guidelines" in body
    assert "[crm] launch-readiness SLA ends 2026-06-21" in body
    assert "Safer alternative" in body
    assert "github.update_milestone_due" in body
    assert "Approvers required (any)" in body
    assert "- engineering lead" in body
    assert "https://court.example.com/runs/t-1?t=sig" in body


@respx.mock
def test_github_failure_surfaces_as_502(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_app(monkeypatch)
    respx.post("https://api.github.com/repos/owner/name/issues/123/comments").mock(
        return_value=httpx.Response(404)
    )
    result = TestClient(module.app).post("/evidence", json=_PACKET)
    assert result.status_code == 502
    assert result.json()["status"] == "error"


def test_missing_configuration_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setenv("GITHUB_REPO", "owner/name")
    monkeypatch.setenv("EVIDENCE_ISSUE", "123")
    sys.modules.pop("scripts.evidence_receiver", None)
    with pytest.raises(RuntimeError, match="GITHUB_TOKEN is required"):
        importlib.import_module("scripts.evidence_receiver")


def test_renderer_imports_without_receiver_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The renderer is pure presentation: tooling previews a ticket comment with no credentials,
    # while the receiver itself keeps failing fast on missing configuration.
    for name in ("GITHUB_TOKEN", "GITHUB_REPO", "EVIDENCE_ISSUE"):
        monkeypatch.delenv(name, raising=False)
    sys.modules.pop("scripts.evidence_markdown", None)
    module = importlib.import_module("scripts.evidence_markdown")
    assert callable(module.render_markdown)


def test_analyzed_packet_renders_conditional_language(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # An analysis-only conclusion: the gate and quorum are reported as what *would* happen, and
    # there is no decision to record.
    module = _load_app(monkeypatch)
    markdown = module.render_markdown({**_PACKET, "event": "analyzed"})
    assert "Change Court — Impact analysis — nothing executed" in markdown
    assert "**Risk:** HIGH — would require approval" in markdown
    assert "**Would-be approvers (any):**" in markdown
    assert "- engineering lead" in markdown
    assert "Approvers required" not in markdown
    assert "**Decision:**" not in markdown
    assert "**Why this is high risk**" in markdown
    assert "- Contract cut-off breach" in markdown
    assert "- Downstream schedule updates" in markdown
    assert "**Policy basis**" in markdown
    assert "Safer alternative" in markdown
    assert "_Analysis only — nothing executed._" in markdown


def test_analyzed_low_risk_renders_the_no_approver_conditional(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_app(monkeypatch)
    markdown = module.render_markdown(
        {
            "event": "analyzed",
            "change": {"raw_request": "create action items from standup"},
            "risk": {"level": "low", "requires_approval": False, "factors": []},
        }
    )
    assert "would need no approver — the requester's confirmation would execute it" in markdown


def test_why_section_falls_back_to_factor_labels(monkeypatch: pytest.MonkeyPatch) -> None:
    # When a gatherer authors no drivers, the "why" lines fall back to the humanized factor labels.
    module = _load_app(monkeypatch)
    markdown = module.render_markdown(
        {
            "event": "analyzed",
            "change": {"raw_request": "grant the vendor access"},
            "risk": {
                "level": "high",
                "requires_approval": True,
                "factors": [
                    {"label": "overbroad_scope", "severity": "high", "citations": []},
                ],
            },
            "impact": {"tags": [], "items": []},
        }
    )
    assert "**Why this is high risk**" in markdown
    assert "- Overbroad scope" in markdown


def test_decided_packet_renders_the_decision(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_app(monkeypatch)
    markdown = module.render_markdown(
        {
            "event": "decided",
            "approved": True,
            "decider": "approver@example.com",
            "note": "approved on the evidence",
            "run_url": None,
        }
    )
    assert "Change Court — Decision recorded" in markdown
    assert "approved by approver@example.com — approved on the evidence" in markdown
