# Deploying the backend and going live in Microsoft 365

The court runs fully locally with mocked integrations and a dev OAuth issuer. To exercise it from
**real** Microsoft 365 Copilot Chat / Teams, the backend must be reachable over public HTTPS and the
MCP server must validate **Entra ID** tokens. This guide covers that path. It assumes the engine is
already green locally (`make check`, `scripts/verify.sh`).

The work splits into two halves that meet at environment variables: **hosting the backend** (below)
and **packaging the declarative agent** (see [`../m365/README.md`](../../m365/README.md)).

## 1. Host the backend over HTTPS

The backend ships a container image (`backend/Dockerfile`) serving `app.asgi:app` — REST health plus
the OAuth2-protected MCP server at `/mcp`. Any host that runs a container and terminates TLS works;
**Azure Container Apps** keeps the agent and its identity in one tenant and is the reference target.

```bash
# Build and push the image (replace the registry/name).
docker build -f backend/Dockerfile -t <registry>/change-court:latest .
docker push <registry>/change-court:latest
```

Deploy it with the environment below, and note the assigned HTTPS hostname (e.g.
`https://change-court.<region>.azurecontainerapps.io`).

For a quick demo without a cloud host, a **dev tunnel** in front of the local backend also gives a
public HTTPS URL:

```bash
uv run uvicorn app.asgi:app --port 8000   # in backend/
devtunnel host -p 8000 --allow-anonymous  # prints an https://...devtunnels.ms URL
```

### Required environment

| Variable | Value |
| --- | --- |
| `PUBLIC_BASE_URL` | The deployed origin, no trailing slash (e.g. `https://change-court.example.com`). The MCP resource URL is derived as `{PUBLIC_BASE_URL}/mcp`. |
| `OAUTH_ISSUER` | `https://login.microsoftonline.com/<tenant-id>/v2.0` |
| `OAUTH_JWKS_URL` | `https://login.microsoftonline.com/<tenant-id>/discovery/v2.0/keys` |
| `OAUTH_AUDIENCE` | The API's Application ID URI, e.g. `api://<app-id>` |
| `DB_URL` | A persistent database. SQLite on ephemeral container storage loses checkpoints on restart — use Postgres (`postgresql+psycopg://…`) for anything beyond a single session. |
| `INTEGRATION_MODE` | Per-system real/mock. Keep mocks for a reliable demo; set `github:real` with `GITHUB_TOKEN`/`GITHUB_REPO` to use a live repo. |

Setting `OAUTH_ISSUER` + `OAUTH_JWKS_URL` automatically switches the MCP server from the local dev
issuer to **Entra ID JWKS validation** (`app/mcp/security.py`); no code change is needed.

When the subscription's tenant and the M365 sign-in tenant differ (a common enterprise topology),
the Terraform module separates them: `azure_tenant_id` places the runtime resources, while
`entra_tenant_id` drives the app registration and the `OAUTH_ISSUER`/`OAUTH_JWKS_URL` values above.

### Optional: agentic roles (Azure OpenAI)

Setting `AZURE_OPENAI_ENDPOINT` + `AZURE_OPENAI_DEPLOYMENT` (keyless via the app's identity, or
`LLM_API_KEY`) switches the court from the deterministic role implementations to the **agentic**
ones: LLM-backed intake parsing, the Prosecutor's validated read-selection loop, and the
Defender's plan drafting within the court's refusal — each with a deterministic fallback, a
per-call timeout, `LLM_MAX_TOKENS`, and the 3-calls-per-trial ceiling (see `reference/adr/0009`). Leave the
endpoint unset and every role stays deterministic.

Keyless requirements: the Container App's user-assigned identity needs the **Cognitive Services
OpenAI User** role on the OpenAI account, and `AZURE_CLIENT_ID` must point at that identity —
Terraform injects it unconditionally, so `DefaultAzureCredential` resolves the right principal
even when only the LLM (and not knowledge grounding) is keyless. The deployment must accept the
`max_tokens` parameter (GPT-4o-class chat deployments do). Watch for silent degradation: if LLM
auth fails every role falls back to deterministic — check the `agentic.*` fallback counters in
`court://metrics` after deploying.

### Optional: knowledge grounding (Azure AI Search)

The impact node can ground its evidence in a knowledge base served by Azure AI Search agentic
retrieval (see [`foundry-iq.md`](foundry-iq.md)). In the deployed app this is wired keylessly:

| Variable | Value |
| --- | --- |
| `KNOWLEDGE_SEARCH_ENDPOINT` | `https://<search>.search.windows.net` |
| `KNOWLEDGE_BASE_NAME` | The knowledge base (agent) name |
| `KNOWLEDGE_SOURCE_NAME` | The knowledge source name |

The Terraform `knowledge_*` variables inject these only when set and grant the Container App's
managed identity **Search Index Data Reader** on the search service and **Cognitive Services OpenAI
User** on the answering OpenAI account (`knowledge_search_resource_id` /
`knowledge_openai_resource_id`) — `DefaultAzureCredential` then authenticates without any secret.
Leave them unset and the backend keeps its offline fallback.

## 2. Register the Entra ID application

In the same tenant (a dedicated **Microsoft 365 dev tenant** with custom-app upload enabled — see
[`adr/0004-development-environment.md`](../reference/adr/0004-development-environment.md)):

1. **App registration** → note the *Application (client) ID* and *Directory (tenant) ID*.
2. **Expose an API** → set the Application ID URI to `api://<app-id>` and add a scope `court.use`
   (the scope the MCP resource server requires). This URI is `OAUTH_AUDIENCE`.
3. **Authentication / token** → the MCP plugin obtains tokens via the Teams OAuth connection; create
   that connection and record its reference id as `OAUTH_CONNECTION_ID` for packaging.
4. If/when real Microsoft Graph adapters are enabled (a later step), add the corresponding **API
   permissions** (e.g. `Calendars.ReadWrite`, `Sites.ReadWrite.All`, `User.Invite.All`) and grant
   admin consent. Mocks need no Graph permissions.

## 3. Bot surface (native approval buttons)

The backend ships a Bot Framework endpoint at `POST {PUBLIC_BASE_URL}/api/messages`. Registered
behind **Azure Bot Service** with a Teams channel, it gives the Change Court card native
`Action.Execute` buttons: the bot proactively delivers the approval card into each approver's
personal chat, the activity-feed toast deep-links onto it, and a click refreshes the card in place
through the same service gates the MCP tools use. Without this registration the flow still works —
approvals just stay narrated text in Copilot Chat.

Terraform automates it (`create_bot = true` in `infra/`); the equivalent manual steps:

1. **Bot app registration** — a **multi-tenant** app (`AzureADMultipleOrgs`) with a client secret.
   Multi-tenant matters in a cross-tenant topology: the Azure Bot resource lives in the
   subscription's tenant while users sign in from the Microsoft 365 tenant. Register it in either
   tenant; note the *Application (client) ID*. (Keep it separate from the court app of step 2 —
   that one is the MCP resource server.)
2. **Azure Bot resource** (in the subscription) — type *Azure Bot*, SKU F0, *Microsoft App ID* =
   the bot app's client id, app type *Multi Tenant*, **messaging endpoint**
   `{PUBLIC_BASE_URL}/api/messages`. Then enable the **Microsoft Teams channel**.
3. **Backend env** — set on the Container App: `BOT_APP_ID`, `BOT_APP_PASSWORD`,
   `BOT_APP_TYPE=MultiTenant` (and `BOT_APP_TENANT_ID` only for a single-tenant bot). Empty
   `BOT_APP_ID` keeps the endpoint in anonymous mode for local Playground use.
4. **Manifest** — export `BOT_APP_ID` before `make package` so the `bots` section resolves, and
   re-upload the app package. On first install in the M365 tenant, Teams prompts consent for the
   multi-tenant bot app — accept it once.
5. **Notifications onto the card** — with `NOTIFY_MODE=teams`, leave `NOTIFY_LINK_URL` empty: the
   toast then deep-links to the bot chat, where the proactive card already sits. Successive
   notifications for the same trial share a `chainId`, so they override rather than stack.

Approvers must have the app installed (so the bot can record where to reach them); anyone who has
not installed it still gets the activity-feed toast and can act from the bot's `queue` command.

## 4. Package and sideload the agent

With the host URL and the values above, build the app package and upload it — see
[`../m365/README.md`](../../m365/README.md) (`make package`). Then walk the three trials in Copilot Chat
and tick off the *Pending tenant* checks in [`../verify.md`](../../verify.md).

## Retention maintenance

Finished trials keep working storage they no longer need: LangGraph checkpoints (one full state
snapshot per node transition) and verdict-claim rows. A retention pass reclaims both — the
append-only audit log is the permanent record and is never touched:

```bash
cd backend && uv run python -m scripts.purge          # uses RETENTION_DAYS (default 30)
uv run python -m scripts.purge --retention-days 7     # explicit window
```

Schedule it (e.g. nightly cron / a Container Apps job) on any deployment that accumulates trials.
The pass is idempotent and bounded: only threads that still hold checkpoints are candidates, so a
cleared backlog costs nothing to re-check.

## Reliability fallback

Real integrations depend on tenant state and quotas. Keep the per-system real/mock toggle
(`INTEGRATION_MODE`, or `FORCE_ALL_MOCK=true`) so a live demo can fall back to the deterministic
mocked path at any time.
