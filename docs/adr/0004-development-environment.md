# ADR-0004: Microsoft 365 surface and knowledge-grounding environment

- **Status:** Proposed (deployment-environment access being confirmed)
- **Date:** 2026-06-02

## Context

The court runs fully locally with mocked integrations and an offline knowledge provider, which is
enough to exercise the three trials end-to-end. Two capabilities, however, depend on an external
environment: surfacing the Change Court in **Microsoft Teams / Copilot Chat**, and **grounding
impact evidence** in real organizational knowledge. We need to decide the target environment for
those without blocking local development.

## Decision

- **Teams surface:** target a **dedicated Microsoft 365 development tenant** (not a production or
  shared tenant) with custom-app upload enabled, reached through a declarative agent + plugin
  manifest pointing at the MCP server. A development tunnel exposes the local backend over HTTPS so
  the tenant can call it.
- **Knowledge grounding:** adopt **Azure AI Foundry (Foundry IQ)** with an Azure AI Search knowledge
  base as the managed knowledge layer, consumed behind a `KnowledgePort`. An offline fake provider
  backs the port during local development, so the engine is knowledge-provider-agnostic and swapping
  fake → Foundry IQ is one adapter with no graph change.
- The Teams/Copilot live path and real knowledge grounding are **deferred extensions** (Phase 4–5);
  they are not on the local critical path.

## Consequences

- Local development and the trials proceed with zero external credentials (`FORCE_ALL_MOCK`, offline
  knowledge fake); the environment dependencies above are isolated to the final phases.
- A readiness check gates the Teams path: a dedicated tenant with admin rights and custom-app upload,
  plus an Azure subscription for the knowledge base. Results are tracked in project planning, not in
  shipped configuration; no credentials are committed.
- Choosing Foundry IQ keeps grounding controllable with a test corpus and avoids any dependency on
  production data or personal information.
