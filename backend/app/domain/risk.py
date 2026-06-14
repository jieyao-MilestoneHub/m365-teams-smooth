"""Risk assessment result, produced deterministically by the policy rule pack."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.domain.enums import RiskLevel


class RiskFactor(BaseModel):
    """One fired risk factor, tied to an evidence tag, carrying its declared severity.

    ``grounded_citations`` carries the governance-policy citations retrieved for the trial —
    advisory context attached after assessment; it never influences the severity, level, or quorum.
    """

    id: str
    label: str
    severity: RiskLevel
    evidence_tag: str
    grounded_citations: list[str] = Field(default_factory=list)


class RiskResult(BaseModel):
    """The risk level (the most severe fired factor) and the factors that produced it."""

    level: RiskLevel
    factors: list[RiskFactor] = Field(default_factory=list)
    requires_approval: bool = False
    matched_rule_ids: list[str] = Field(default_factory=list)
