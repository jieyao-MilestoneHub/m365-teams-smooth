"""An authenticated actor — the requester who opens a trial or an approver who votes on it."""

from __future__ import annotations

from pydantic import BaseModel


class Principal(BaseModel):
    """A person acting on a trial, identified by their Entra claims.

    Identity comparison uses :meth:`key`, which prefers the immutable ``oid`` and falls back to the
    user principal name, so identities compare by a stable key rather than display name.
    """

    oid: str = ""
    upn: str = ""
    display_name: str = ""

    def key(self) -> str:
        """Stable lowercased identity key (oid → upn → display_name)."""
        return (self.oid or self.upn or self.display_name).strip().lower()

    def same_as(self, other: Principal | None) -> bool:
        """True when ``other`` is the same identity (and both are non-empty)."""
        return other is not None and bool(self.key()) and self.key() == other.key()
