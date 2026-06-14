"""The pack-derived grounding map stays aligned with the gatherers, byte for byte."""

from __future__ import annotations

from app.agent.gatherers import GATHERERS
from app.agent.policy_rules.models import MatchRules, RulePack
from app.agent.policy_rules.packs import default_packs
from app.agent.policy_rules.vocabulary import grounding_queries


def test_every_registered_gatherer_subject_has_a_grounding_phrase() -> None:
    assert set(grounding_queries(default_packs())) == set(GATHERERS)


def test_default_phrases_are_pinned() -> None:
    # The offline byte-identity guard: these exact phrases reach knowledge.ground, so changing
    # one is a deliberate decision (re-validate with scripts/eval_retrieval.py), never drift.
    assert grounding_queries(default_packs()) == {
        "launch": "schedule change controlled coordinated milestone date",
        "sso-ga": "SSO GA promise security review sign-off",
        "project-access": "vendor access least privilege scope expiry",
        "meeting-actions": "meeting follow-through action item owner due date accountability",
        "weekly-report": "status reporting weekly cadence single source of record",
    }


def _pack(pack_id: str, subjects: list[str], query: str) -> RulePack:
    return RulePack(
        id=pack_id,
        match=MatchRules(),
        subjects=subjects,
        grounding_query=query,
    )


def test_first_pack_claiming_a_subject_wins() -> None:
    # Mirrors the policy node's first-match pack selection.
    packs = [_pack("a", ["x"], "first phrase"), _pack("b", ["x", "y"], "second phrase")]
    assert grounding_queries(packs) == {"x": "first phrase", "y": "second phrase"}


def test_a_pack_without_a_phrase_contributes_nothing() -> None:
    assert grounding_queries([_pack("a", ["x"], "")]) == {}
