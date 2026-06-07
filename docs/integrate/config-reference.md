# Configuration reference — the integration-relevant environment variables

Everything is env-driven through `backend/app/config.py` (pydantic-settings).
[`.env.example`](../../.env.example) is the authoritative, commented template — this page groups
the variables by integration concern so you can find the right knob fast. Deployment-only concerns
(hosting, icons, sideloading) live in [deploy/deploy.md](../deploy/deploy.md) and the
[runbook](../deploy/runbook.md).

## Integrations (adapters)

| Variable | Default | Meaning |
| --- | --- | --- |
| `INTEGRATION_MODE` | `github:real` | Per-system real/mock selection, comma-separated `system:mode`. Unlisted systems are mock. |
| `FORCE_ALL_MOCK` | `false` | Kill-switch: every integration (and knowledge/LLM) runs mocked — zero external credentials. |
| `DRY_RUN_DEFAULT` | `true` | Whether new decisions default to dry-run (predicted effects, no side effects). |
| `GITHUB_TOKEN` / `GITHUB_REPO` | empty | Real GitHub adapter only; scope the token to a throwaway `owner/name` repo. |

## Microsoft Graph (real evidence reads)

| Variable | Meaning |
| --- | --- |
| `GRAPH_TENANT_ID` / `GRAPH_CLIENT_ID` / `GRAPH_CLIENT_SECRET` | App-only auth for the real Outlook/SharePoint read adapters (admin-consented `Calendars.Read`, `Sites.Read.All`). |
| `OUTLOOK_CALENDAR_UPN` | The user whose calendar supplies seeded evidence events. |
| `SHAREPOINT_SITE_ID` | The site whose library supplies folder evidence. |

## Knowledge grounding (Foundry IQ)

| Variable | Meaning |
| --- | --- |
| `KNOWLEDGE_SEARCH_ENDPOINT` | Azure AI Search endpoint; empty → offline fake provider. Keyless auth (`DefaultAzureCredential`) — no key variable exists. |
| `KNOWLEDGE_BASE_NAME` / `KNOWLEDGE_SOURCE_NAME` | The Foundry IQ knowledge base and source to retrieve from. |

Details: [foundry-iq.md](foundry-iq.md).

## LLM provider

| Variable | Meaning |
| --- | --- |
| `AZURE_OPENAI_ENDPOINT` / `AZURE_OPENAI_DEPLOYMENT` / `AZURE_OPENAI_API_VERSION` | Enable the LLM-backed agentic parser; keyless auth unless a key is set. |
| `LLM_API_KEY` / `LLM_MODEL` | Key-based alternative; empty → offline deterministic provider. |
| `LLM_TIMEOUT_SECONDS` | Per-call cap; on expiry the node falls back to deterministic parsing. |

Details: [llm-provider.md](llm-provider.md).

## Approvals & notifications

| Variable | Meaning |
| --- | --- |
| `APPROVER_DIRECTORY` | Role → identities mapping (comma-separated pairs) that quorum roles resolve against. |
| `NOTIFY_MODE` | `off` (default) or `teams` — push approval events to the Teams activity feed via Graph (needs `TeamsActivity.Send`). Best-effort; never blocks the workflow. |
| `NOTIFY_LINK_URL` / `NOTIFY_TEAMS_APP_ID` | Toast click-through target (must be a Teams deep link) and the catalog app id. |
| `BOT_APP_ID` / `BOT_APP_PASSWORD` / `BOT_APP_TYPE` / `BOT_APP_TENANT_ID` | The bot registration behind the card's native approval buttons; all empty → anonymous local Playground auth. |

## Surfaces & security

| Variable | Meaning |
| --- | --- |
| `OAUTH_ISSUER` / `OAUTH_AUDIENCE` / `OAUTH_JWKS_URL` | MCP OAuth2 resource-server settings (Entra ID in a tenant); unset → local dev issuer. |
| `RUN_LINK_SECRET` | HMAC secret signing the read-only run-page links; empty disables the page. |
| `PUBLIC_BASE_URL` | Public HTTPS origin; the agent calls `{PUBLIC_BASE_URL}/mcp`. |
| `DB_URL` | SQLAlchemy URL — SQLite locally, Postgres later; nothing else changes. |

## Bounds & observability

| Variable | Default | Meaning |
| --- | --- | --- |
| `GRAPH_TIMEOUT_SECONDS` | `60` | Wall-clock guard on a single pipeline run (checkpoint stays resumable). |
| `HTTP_TIMEOUT_SECONDS` | `10` | Default adapter request timeout. |
| `RETRY_MAX_ATTEMPTS` / `RETRY_BACKOFF_*` | `3` / `0.2–2s` | Idempotency-aware adapter retry policy. |
| `RETENTION_DAYS` | `30` | Working-storage purge window — never touches the audit. |
| `METRICS_ENABLED` | `true` | Exposes the in-process registry as `court://metrics`. |
| `LOG_LEVEL` / `LOG_FORMAT` | `INFO` / `json` | Logging verbosity and shape. |
