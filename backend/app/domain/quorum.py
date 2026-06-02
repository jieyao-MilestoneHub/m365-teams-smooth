"""Quorum: who must approve, and the verdict options offered to them."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.domain.enums import ApproverRole, VerdictType


class Approver(BaseModel):
    """A required approver, derived from an impact tag by the rule pack."""

    role: ApproverRole
    reason: str = ""
    derived_from_tag: str = ""


class VerdictOption(BaseModel):
    """One choice a reviewer may cast."""

    type: VerdictType
    label: str = ""


class Quorum(BaseModel):
    """The required approvers and the available verdict options."""

    required_approvers: list[Approver] = Field(default_factory=list)
    verdict_options: list[VerdictOption] = Field(default_factory=list)
    policy: Literal["all", "any"] = "all"
