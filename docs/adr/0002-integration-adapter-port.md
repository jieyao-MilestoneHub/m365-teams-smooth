# ADR-0002: IntegrationAdapter port as the integration boundary

- **Status:** Accepted
- **Date:** 2026-06-02

## Context

The court reads cross-system evidence and writes cross-system actions. Integrations differ wildly
(GitHub API, mock Outlook/Planner/SharePoint/Teams/CRM/Entra), some real and some mocked, chosen per
system from configuration. The agent and services must not depend on any integration SDK, and adding
an integration must not require edits to the graph, services, REST, or MCP.

## Decision

Define a single `IntegrationAdapter` port with `capabilities() / validate() / read(query) /
execute(step, mode) / fetch_before() / suggest_rollback()`. Capabilities are typed and split into
**read** (evidence for the impact node) and **write** (actions for execution). A
`BaseIntegrationAdapter` template-methods the dry-run branch and maps SDK errors to a typed
`IntegrationError` in one place. An `IntegrationRegistry` selects real-vs-mock per system from
config (`integration_mode`, plus `FORCE_ALL_MOCK`).

## Consequences

- A new integration = one adapter module + one registration (Open/Closed); no edits elsewhere.
- `run_mode` (DRY_RUN/LIVE) is a state field handled once in the base class — no separate code path.
- Only the adapters the three trials need are built; others are backlog.
