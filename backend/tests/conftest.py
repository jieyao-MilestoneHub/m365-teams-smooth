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
from app.domain import AuditRecord
from app.ports.integration import IntegrationAdapter
from app.ports.repository import AuditRepository, VerdictLedger


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
