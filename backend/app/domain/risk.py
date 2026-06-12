"""Risk scoring result, produced deterministically by the policy rule pack."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.domain.enums import RiskLevel


class RiskFactor(BaseModel):
    """One scored contribution, tied to an evidence tag.

    ``grounded_citations`` carries the governance-policy citations retrieved for the trial —
    advisory context attached after scoring; it never influences the score, level, or quorum.
    """

    id: str
    label: str
    weight: int
    evidence_tag: str
    grounded_citations: list[str] = Field(default_factory=list)


class RiskResult(BaseModel):
    """The banded risk level, the score, and the factors that produced it."""

    level: RiskLevel
    score: int
    factors: list[RiskFactor] = Field(default_factory=list)
    requires_approval: bool = False
    matched_rule_ids: list[str] = Field(default_factory=list)
