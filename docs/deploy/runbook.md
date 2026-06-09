# Deploy runbook — Azure Container Apps → Teams demo

A copy-paste runbook from source to a **stable, machine-independent** Teams demo: provision the
backend on Azure Container Apps, enable the agentic + approval features, wire the Teams entry point,
run the trials in Copilot Chat. Once applied the demo works with your laptop off (fixed FQDN, compute
in Azure). For a throwaway "does it work today" test, the dev-tunnel path in [`deploy.md`](deploy.md)
is faster; this is the real, repeatable path.

> Conventions: run from the **repo root** unless noted; `terraform` commands run in `infra/`; values
> flow between steps via `terraform output`.

---

## Phase 0 — Prerequisites (once)

- **Tooling:** Azure CLI (`az`), Terraform ≥ 1.5, Docker, Python/uv. `az login` to the subscription
  that will host the runtime; you also need rights to create an **Entra app registration** in the
  M365 sign-in tenant.
- **Tenants** (may be the same or different — the module supports both):
  - `azure_tenant_id` — the Azure subscription's tenant (runtime resources).
  - `entra_tenant_id` — the M365 tenant users sign in to (app registration, OAuth). For this
    project that is `agentleague` → `ce383846-da17-481d-8306-22dbfed87ff7`.
- **M365 tenant** with **custom-app upload enabled**. To *use* a declarative agent that has actions
  (this one calls an MCP), each demo account needs **either** a Microsoft 365 Copilot license **or**
  the tenant must have **pay-as-you-go (metered) billing** connected to Copilot Chat (see Phase 5).
  A base Microsoft 365 license (e.g. Business Basic) plus pay-as-you-go is enough for testing.
- **Icons:** add `m365/color.png` (192×192) and `m365/outline.png` (32×32) — packaging fails without them.
- **Cross-tenant deploys** (the deployer's identity cannot create the Entra app in the M365 tenant —
  e.g. the runtime subscription lives in a different tenant): set `create_entra_app = false` and
  register the Entra app in the M365 tenant separately, then pass its `entra_client_id` in
  `terraform.tfvars`. The `azuread` provider then creates nothing and authenticates against
  `azure_tenant_id`. Expose an `api://<client-id>/court.use` scope and a Teams redirect URI on that
  app; it backs both `OAUTH_AUDIENCE` and the Phase 3 OAuth connection.
- **A chat LLM powers the agentic roles** (Prosecutor/Defender/precedent reasoning) — configure one
  to demonstrate the agent; the reference uses **Azure OpenAI** (GPT-4o-class, `max_tokens`), other
  providers plug in via the `LLMProvider` port (one adapter, not config-only —
  [llm-provider.md](../integrate/llm-provider.md)). Without it the deterministic fallback still runs
  the trials, but shows no agentic reasoning. *(Optional)* a throwaway GitHub repo (`Launch Rehearsal`
  milestone + closed issues) for live GitHub evidence.

---

## Phase 1 — Provision the backend (Container Apps)

```bash
cd infra
cp terraform.tfvars.example terraform.tfvars
# edit terraform.tfvars: subscription_id, azure_tenant_id, entra_tenant_id, location
#   keep force_all_mock = true for the most reliable first demo (no Graph creds needed)
#   set min_replicas = 1 if you want zero cold-start during the demo

terraform init

# 1) Registry first, so the image has somewhere to live.
terraform apply -target=azurerm_container_registry.this

# 2) Build and push the backend image to the new ACR (from repo root).
ACR=$(terraform output -raw acr_login_server)
az acr login --name "${ACR%%.*}"
docker build -f ../backend/Dockerfile -t "$ACR/change-court:latest" ..
docker push "$ACR/change-court:latest"

# 3) Create everything else (Container App + Entra app registration).
terraform apply
```

The image serves `app.asgi:app` (REST health **+** the OAuth2 MCP server at `/mcp`) as a non-root
user — verified by PR #236. Confirm the deployment:

```bash
BASE=$(terraform output -raw public_base_url)
curl -s -o /dev/null -w '%{http_code}\n' "$BASE/api/health"        # 200
curl -s -o /dev/null -w '%{http_code}\n' -X POST "$BASE/mcp/"       # 401 (mounted + auth-protected)
```

A `401` on `/mcp/` is success — it means the MCP server is mounted and demanding a token. A `404`
would mean the wrong app is being served (see Troubleshooting).

---

## Phase 2 — Enable the agentic roles and approval enforcement

The agentic roles (Prosecutor read-selection, Defender planning, precedent memory) and separation of
duties are enabled **through Terraform** — set them in `terraform.tfvars` (Phase 1) and they ship
with the `apply`, no post-deploy `az` step. The key coupling: the agentic roles require
`force_all_mock = false` (it otherwise disables them), so for a reliable *full-functionality* demo
keep the integrations mocked via `integration_mode` while turning the LLM on:

```hcl
# terraform.tfvars
force_all_mock          = false              # required — otherwise the agentic roles stay off
integration_mode        = "github:mock"      # reliable mocks; "github:real" for live blocker evidence
azure_openai_endpoint   = "https://<your>.openai.azure.com"
azure_openai_deployment = "gpt-4o"           # must accept the max_tokens parameter
llm_api_key             = "<azure-openai-key>"   # demo route; omit for keyless (see note)
approver_directory      = "eng_lead:<approver-upn>,comms:<approver-upn>,security_lead:<approver-upn>,account_owner:<approver-upn>,manager:<approver-upn>"
notify_mode             = "teams"            # best-effort approval toasts via the Graph activity feed
notify_teams_app_id     = "<teams-app-catalog-id>"
```

Then `terraform apply` (Phase 1 step 3, or re-apply if you set these after the first apply).
`DRY_RUN_DEFAULT` stays true, so every write is predicted — the demo is safe.

> `terraform.tfvars` must stay **complete**: each secret and optional surface (graph/bot/notify) is
> conditional on its variable, so re-applying with one left blank removes it from the live app. If an
> instance was tuned with `az` after the original apply, push a new build with
> `az containerapp update --image` rather than a blind `apply`, and reconcile deliberately later —
> see [`../../infra/README.md`](../../infra/README.md) (*Updating vs reconciling*).

Notes:
- **Keyless instead of a key** (preferred for production): omit `llm_api_key`, and grant the
  Container App's managed identity the **Cognitive Services OpenAI User** role on the OpenAI account
  (`AZURE_CLIENT_ID` is already injected by the module). The key route avoids the role-assignment
  round-trip for a quick demo.
- **Leaving these empty** keeps the deterministic, fully-mocked court (still a valid demo, just not
  the agentic/2-user one).
- Approver accounts created *after* the first apply: add them to `approver_directory` and re-run
  `terraform apply` (or `az containerapp update --set-env-vars APPROVER_DIRECTORY=...`).

---

## Phase 3 — Teams OAuth connection (the one manual piece)

Terraform creates the Entra app and the `court.use` scope, but the **Teams-side OAuth connection**
cannot be created by Terraform. Pull the values and register it:

```bash
terraform output entra_client_id
terraform output court_scope                 # api://<client-id>/court.use
terraform output -raw entra_client_secret    # sensitive
terraform output oauth_issuer                # authorize/token endpoints derive from this
```

In the Teams Developer Portal (or Agents Toolkit) → your app → **OAuth client registration**, create
a connection using the client id, the client secret, `court.use`, and the tenant authorize/token
endpoints. It yields a **connection reference id** → this is `OAUTH_CONNECTION_ID` for packaging.

---

## Phase 4 — Package and sideload the declarative agent

```bash
TEAMS_APP_ID=$(uuidgen) \
MCP_HOST_DOMAIN=$(terraform -chdir=infra output -raw mcp_host_domain) \
MCP_SERVER_URL=$(terraform -chdir=infra output -raw mcp_server_url) \
OAUTH_CONNECTION_ID=<from Phase 3> \
make package
# -> wrote m365/build/appPackage.zip
```

Upload `m365/build/appPackage.zip` to the M365 tenant (Teams → Apps → Manage your apps → Upload a
custom app, or via Agents Toolkit). The declarative agent now appears in Copilot Chat.

---

## Phase 5 — Run the demo in Teams

> **Prerequisite to *use* the agent — Copilot entitlement.** A declarative agent with actions is
> gated until the account is entitled: assign a Microsoft 365 Copilot license, or connect
> **pay-as-you-go** (M365 admin centre → Copilot → Billing & usage → a billing policy scoped to the
> demo accounts → connect to Copilot Chat). Propagation can take ~2 hours.
> See [pay-as-you-go/setup](https://learn.microsoft.com/en-us/copilot/microsoft-365/pay-as-you-go/setup).

Then run the demo in Copilot Chat / Teams. The step-by-step **recording script** — the single
Informed Approval scenario beat by beat, the windows to capture, the expected effect of each, and
the second-screen run page — is in
[`docs/demo/recording-runbook.md`](../demo/recording-runbook.md); the two-user approval flow and its
negative cases (no self-approval; outside-directory cannot decide) are in
[`two-user-demo.md`](../demo/two-user-demo.md). Per-trial expected outcomes: [`trials.md`](../reference/trials.md).

**Day-of prep** (deploy-first rule, data resets, conversation re-registration, warm-up, smoke) is the
ordered checklist in [`docs/demo/demo-day-checklist.md`](../demo/demo-day-checklist.md): the Container
App's SQLite is ephemeral — deploy first, freeze deploys, then do everything stateful.

---

## Troubleshooting

| Symptom | Cause → fix |
|---|---|
| `/mcp/` returns **404** | Container serving the wrong app. The image must serve `app.asgi:app` (PR #236). Rebuild/push and `terraform apply`. |
| `/mcp/` returns **401** | Expected — it is mounted and auth-protected. The declarative agent supplies the token. |
| Agent answers but never refuses / no agentic evidence | `AZURE_OPENAI_*` not set or auth failing → roles fell back to deterministic. Check Phase 2 env and `court://metrics` `agentic.*` counters. |
| `decide` rejected with `unauthorized_approver` | The approver's identity is not in `APPROVER_DIRECTORY`, or it matches the requester (self-approval is forbidden by design). |
| `make package` errors on placeholders | One of `TEAMS_APP_ID` / `MCP_HOST_DOMAIN` / `MCP_SERVER_URL` / `OAUTH_CONNECTION_ID` is unset (Phase 4), or icons are missing (Phase 0). |
| First call after idle is slow | Cold start from `min_replicas = 0`; set `min_replicas = 1` for the demo window. |

## Known issues (open — plan around these)

- **Activity-feed toast action is inert** — a declarative agent has no in-Teams surface to land on;
  the approver opens Copilot Chat and runs `list_pending_approvals`. (Microsoft —
  [Copilot extensibility known issues](https://learn.microsoft.com/en-us/microsoft-365/copilot/extensibility/known-issues).)
- **A package update needs remove + re-add** — Copilot caches the manifest + auth: remove, fully quit
  Teams, re-add from "Built for your org", re-consent. Never ship one on demo day. (Microsoft —
  [Copilot extensibility known issues](https://learn.microsoft.com/en-us/microsoft-365/copilot/extensibility/known-issues).)
- **`APPROVER_DIRECTORY` must use the Entra oid, not the UPN** — a Teams bot activity carries the
  user's `aadObjectId`, and the conversation reference is stored by it; a UPN entry misses
  (`proactive.skipped`). (Microsoft — [Send proactive messages](https://learn.microsoft.com/en-us/microsoftteams/platform/bots/how-to/conversations/send-proactive-messages).)
- **An agent silently won't call the tool** (no `POST /mcp` logged) — a client-side cache/consent
  issue, not the backend: diagnose with `-developer on`; fixes: remove + re-add the app, or clear the
  persisted OAuth token. (Microsoft — [Troubleshoot MCP apps](https://learn.microsoft.com/en-us/microsoft-365/copilot/extensibility/plugin-mcp-apps-troubleshooting).)
