"""The ticket demo drives analyze → packet → escalation end to end, credential-free."""

from __future__ import annotations

import pytest

from scripts.demo_ticket import run


def test_both_acts_deliver_their_packets_to_the_ticket(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("EVIDENCE_WEBHOOK_URL", raising=False)
    packets = run()

    events = [p["event"] for p in packets]
    assert events == ["analyzed", "analyzed", "approval_requested", "decided"]

    # Act 1, high risk: the would-be gate and quorum are in the packet; nothing executed,
    # nothing decided.
    breach = packets[0]
    risk = breach["risk"]
    assert isinstance(risk, dict) and risk["requires_approval"] is True
    quorum = breach["quorum"]
    assert isinstance(quorum, dict)
    assert set(quorum["required_roles"]) == {"eng_lead", "comms", "account_owner"}
    assert "verdict" not in breach
    assert "results" not in breach

    # Act 1, routine: the packet itself shows zero would-be approvers.
    routine = packets[1]
    routine_quorum = routine.get("quorum")
    assert not isinstance(routine_quorum, dict) or routine_quorum["required_roles"] == []

    # Act 2: the same webhook carries the approval round-trip to the same ticket.
    decided = packets[3]
    assert decided["approved"] is True
    assert "results" in decided

    out = capsys.readouterr().out
    assert "Impact analysis — nothing executed" in out
    assert "Would-be approvers" in out
    assert "github.github." not in out  # step labels carry one system prefix, not two


def test_analyze_only_stops_after_the_evidence(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("EVIDENCE_WEBHOOK_URL", raising=False)
    packets = run(analyze_only=True)
    assert [p["event"] for p in packets] == ["analyzed", "analyzed"]
    assert "Act 2" not in capsys.readouterr().out
