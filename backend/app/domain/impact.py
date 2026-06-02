"""Impact evidence: the second-order consequences the impact node gathers."""

from __future__ import annotations

from pydantic import BaseModel, Field


class GroundedFact(BaseModel):
    """A fact returned by the knowledge provider, with a citation."""

    claim: str
    source_id: str
    citation: str = ""


class EvidenceItem(BaseModel):
    """One consequence found via a read capability."""

    system: str
    kind: str
    summary: str
    severity: str = "info"
    data: dict[str, object] = Field(default_factory=dict)
    grounded: list[GroundedFact] = Field(default_factory=list)


class ImpactEvidence(BaseModel):
    """The collected evidence plus the machine-readable tags policy/quorum match on."""

    items: list[EvidenceItem] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
