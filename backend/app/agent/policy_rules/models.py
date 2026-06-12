"""Rule-pack data model. Packs are validated data, not code; the policy node interprets them."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.domain import ApproverRole, VerdictType

# Injected into the fired-tag set when no pack governs a change, so the UNGOVERNED fallback
# pack's factor and quorum rules fire data-driven (the policy node adds no scoring semantics).
UNGOVERNED_TAG = "governance.ungoverned"


class MatchRules(BaseModel):
    """How a pack is selected for a change."""

    any_action_capability: list[str] = Field(default_factory=list)
    any_tag: list[str] = Field(default_factory=list)


class RiskFactorRule(BaseModel):
    """An additive risk contribution keyed on an evidence tag."""

    id: str
    when_tag: str
    weight: int
    marks_unsafe: bool = False


class RiskBands(BaseModel):
    """Score thresholds that band the total into a RiskLevel."""

    low: int = 0
    medium: int
    high: int


class ApproverRule(BaseModel):
    """A required approver added when its tag fires."""

    role: ApproverRole
    when_tag: str


class QuorumRules(BaseModel):
    """Approver derivation rules and the approval policy."""

    approvers: list[ApproverRule] = Field(default_factory=list)
    policy: Literal["all", "any"] = "all"


class VerdictOptionRules(BaseModel):
    """The verdict options offered, selected by outcome."""

    default: list[VerdictType] = Field(default_factory=list)
    when_unsafe: list[VerdictType] = Field(default_factory=list)
    when_high_risk_internal: list[VerdictType] = Field(default_factory=list)


class RulePack(BaseModel):
    """One trial family's risk, quorum, and verdict rules."""

    id: str
    match: MatchRules = Field(default_factory=MatchRules)
    risk_factors: list[RiskFactorRule] = Field(default_factory=list)
    risk_bands: RiskBands
    quorum: QuorumRules = Field(default_factory=QuorumRules)
    verdict_options: VerdictOptionRules = Field(default_factory=VerdictOptionRules)
    # The parser subjects this pack specializes (informational + the grounding key); empty for
    # packs that match purely on capabilities/tags (and for the UNGOVERNED fallback).
    subjects: list[str] = Field(default_factory=list)
    # Targeted knowledge-retrieval phrase for those subjects ("" -> raw-request grounding).
    grounding_query: str = ""
