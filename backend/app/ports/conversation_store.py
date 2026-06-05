"""The conversation-store port: where a user can be reached for proactive bot messages.

The bot surface records each user's serialized Bot Framework conversation reference when they
install or talk to the bot; the proactive notifier looks the reference up by identity to deliver
the actionable approval card into that user's chat. The store is a seam: SQL today, anything
addressable later, without touching the bot or the notifiers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class ConversationStore(ABC):
    """Persists Bot Framework conversation references keyed by user identity."""

    @abstractmethod
    def save(self, *, oid: str, upn: str, reference: dict[str, object]) -> None:
        """Record ``reference`` for the user, addressable by ``oid`` and lowercased ``upn``."""

    @abstractmethod
    def get(self, identity: str) -> dict[str, object] | None:
        """The stored reference for ``identity`` (an oid or a upn, case-insensitive), if any."""
