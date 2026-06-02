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
from app.ports.integration import IntegrationAdapter


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
