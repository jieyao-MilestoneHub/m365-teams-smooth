"""Shared fixtures: a fully-mocked integration registry and the offline providers."""

from __future__ import annotations

import pytest

from app.adapters.integrations.mock_crm import MockCRMAdapter
from app.adapters.integrations.mock_entra import MockEntraAdapter
from app.adapters.integrations.mock_github import MockGitHubAdapter
from app.adapters.integrations.mock_outlook import MockOutlookAdapter
from app.adapters.integrations.mock_planner import MockPlannerAdapter
from app.adapters.integrations.mock_sharepoint import MockSharePointAdapter
from app.adapters.integrations.mock_teams import MockTeamsAdapter
from app.adapters.integrations.registry import ConfigIntegrationRegistry
from app.adapters.knowledge.fake_knowledge import FakeKnowledgeProvider
from app.adapters.llm.fake_llm import FakeLLMProvider
from app.domain import ApprovalDecision, ApprovalEvent, AuditRecord
from app.ports.conversation_store import ConversationStore
from app.ports.integration import IntegrationAdapter
from app.ports.repository import ApprovalLedger, AuditRepository, VerdictLedger


class InMemoryAuditRepository(AuditRepository):
    """In-memory append-only audit log for tests."""

    def __init__(self) -> None:
        self.records: list[AuditRecord] = []

    def append(self, record: AuditRecord) -> None:
        self.records.append(record)

    def get(self, audit_id: str) -> AuditRecord | None:
        return next((r for r in self.records if r.audit_id == audit_id), None)

    def latest_for_change(self, change_id: str) -> AuditRecord | None:
        matches = [r for r in self.records if r.change_id == change_id]
        return matches[-1] if matches else None

    def thread_ids_completed_before(self, cutoff: str) -> list[str]:
        latest: dict[str, str] = {}
        for r in self.records:
            latest[r.thread_id] = max(latest.get(r.thread_id, ""), r.created_at)
        return [tid for tid, at in latest.items() if at < cutoff]


class InMemoryVerdictLedger(VerdictLedger):
    """In-memory exactly-once verdict ledger for tests."""

    def __init__(self) -> None:
        self._claims: dict[tuple[str, str], str | None] = {}

    def try_claim(self, thread_id: str, idempotency_key: str) -> bool:
        key = (thread_id, idempotency_key)
        if key in self._claims:
            return False
        self._claims[key] = None
        return True

    def mark_completed(self, thread_id: str, idempotency_key: str, audit_id: str) -> None:
        self._claims[(thread_id, idempotency_key)] = audit_id

    def result_for(self, thread_id: str, idempotency_key: str) -> str | None:
        return self._claims.get((thread_id, idempotency_key))

    def purge_thread(self, thread_id: str) -> None:
        self._claims = {k: v for k, v in self._claims.items() if k[0] != thread_id}


class InMemoryApprovalLedger(ApprovalLedger):
    """In-memory approval-event log + pending index for tests (mirrors SqlApprovalLedger)."""

    def __init__(self) -> None:
        self.events: list[ApprovalEvent] = []
        self._pending: dict[str, str] = {}  # thread_id -> created_at

    def append(self, event: ApprovalEvent) -> None:
        self.events.append(event)

    def list_for_thread(self, thread_id: str) -> list[ApprovalEvent]:
        return [e for e in self.events if e.thread_id == thread_id]

    def thread_ids(self) -> list[str]:
        seen: list[str] = []
        for event in self.events:
            if event.thread_id not in seen:
                seen.append(event.thread_id)
        return seen

    def first_note(self, thread_id: str, decision: ApprovalDecision) -> str:
        for event in self.events:
            if event.thread_id == thread_id and event.decision is decision:
                return event.note
        return ""

    def mark_pending(self, thread_id: str, at: str) -> None:
        self._pending.setdefault(thread_id, at)

    def clear_pending(self, thread_id: str) -> None:
        self._pending.pop(thread_id, None)

    def pending_thread_ids(self) -> list[str]:
        return sorted(self._pending, key=lambda t: self._pending[t])


class InMemoryConversationStore(ConversationStore):
    """In-memory conversation references for tests (mirrors SqlConversationStore keying)."""

    def __init__(self) -> None:
        self.references: dict[str, dict[str, object]] = {}

    def save(self, *, oid: str, upn: str, reference: dict[str, object]) -> None:
        for key in {k for k in (oid.strip(), upn.strip().lower()) if k}:
            self.references[key] = reference

    def get(self, identity: str) -> dict[str, object] | None:
        key = identity.strip()
        return self.references.get(key) or self.references.get(key.lower())


def build_mock_registry(*, planner_fail_on: str | None = None) -> ConfigIntegrationRegistry:
    """A registry holding all seven mock adapters (the fully-mocked trial environment)."""
    adapters: list[IntegrationAdapter] = [
        MockGitHubAdapter(),
        MockOutlookAdapter(),
        MockPlannerAdapter(fail_on=planner_fail_on),
        MockSharePointAdapter(),
        MockTeamsAdapter(),
        MockCRMAdapter(),
        MockEntraAdapter(),
    ]
    return ConfigIntegrationRegistry(adapters)


@pytest.fixture
def mock_registry() -> ConfigIntegrationRegistry:
    return build_mock_registry()


@pytest.fixture
def knowledge() -> FakeKnowledgeProvider:
    return FakeKnowledgeProvider()


@pytest.fixture
def llm() -> FakeLLMProvider:
    return FakeLLMProvider()
