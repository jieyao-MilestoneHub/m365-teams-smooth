"""The conversation store answers by oid or UPN (case-insensitive) and rewrites on every save."""

from __future__ import annotations

from app.adapters.persistence.db import make_engine, make_session_factory
from app.adapters.persistence.models import Base
from app.adapters.persistence.repositories import SqlConversationStore


def _store() -> SqlConversationStore:
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return SqlConversationStore(make_session_factory(engine))


def test_roundtrip_by_oid_and_upn_case_insensitive() -> None:
    store = _store()
    reference: dict[str, object] = {
        "conversation": {"id": "conv-1"},
        "service_url": "https://example.test",
    }
    store.save(oid="oid-1", upn="Approver@Example.com", reference=reference)

    assert store.get("oid-1") == reference
    assert store.get("approver@example.com") == reference
    assert store.get("APPROVER@EXAMPLE.COM") == reference
    assert store.get("someone-else") is None


def test_save_overwrites_with_the_latest_reference() -> None:
    store = _store()
    store.save(oid="oid-1", upn="user@example.com", reference={"conversation": {"id": "old"}})
    store.save(oid="oid-1", upn="user@example.com", reference={"conversation": {"id": "new"}})

    got = store.get("user@example.com")
    assert got is not None and got["conversation"] == {"id": "new"}


def test_blank_identities_are_ignored() -> None:
    store = _store()
    store.save(oid="", upn="  ", reference={"conversation": {"id": "x"}})
    assert store.get("") is None
    assert store.get("x") is None
