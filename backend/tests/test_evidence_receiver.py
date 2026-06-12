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
        "score": 80,
        "requires_approval": True,
        "factors": [
            {
                "id": "m",
                "label": "milestone move",
                "weight": 80,
                "evidence_tag": "schedule.milestone_move",
                "citations": ["GOV-1"],
            }
        ],
    },
    "impact": {
        "tags": ["schedule.milestone_move"],
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
    assert "milestone move (+80) — GOV-1" in body
    assert "[crm] launch-readiness SLA ends 2026-06-21" in body
    assert "Safer alternative" in body
    assert "github.update_milestone_due" in body
    assert "Approvers required (any)" in body
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
