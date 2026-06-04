"""Resolves which approver roles an authenticated principal holds.

Config-backed (role → identities), mirroring the env-driven style of ``config.py``. A future
``ports/`` seam can swap in Microsoft Graph group resolution without touching the service.
"""

from __future__ import annotations

from collections.abc import Iterable

from app.config import Settings
from app.domain.enums import ApproverRole
from app.domain.principal import Principal

_VALID_ROLES = {r.value for r in ApproverRole}


class ApproverDirectory:
    """Maps approver roles to the identities authorized to act in them."""

    def __init__(self, role_members: dict[str, set[str]]) -> None:
        # Keep only known roles; identity keys are already lowercased by the parser.
        self._members = {r: ids for r, ids in role_members.items() if r in _VALID_ROLES}

    @classmethod
    def from_settings(cls, settings: Settings) -> ApproverDirectory:
        return cls(settings.approver_map())

    def configured(self) -> bool:
        """True when at least one role→identity mapping exists (enforcement is meaningful)."""
        return any(self._members.values())

    def roles_for(self, principal: Principal) -> set[ApproverRole]:
        """The approver roles this principal holds (matched on oid or upn)."""
        keys = {principal.oid.strip().lower(), principal.upn.strip().lower()} - {""}
        return {
            ApproverRole(role) for role, ids in self._members.items() if ids & keys
        }

    def is_authorized(self, principal: Principal, required: Iterable[ApproverRole]) -> bool:
        """True when the principal holds at least one of the required roles."""
        return bool(self.roles_for(principal) & set(required))

    def identities_for(self, roles: Iterable[ApproverRole]) -> set[str]:
        """Identity keys (oid or upn, lowercased) of everyone holding any of ``roles``."""
        wanted = {role.value for role in roles}
        identities: set[str] = set()
        for role, ids in self._members.items():
            if role in wanted:
                identities |= ids
        return identities
