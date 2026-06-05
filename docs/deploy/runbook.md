# Deploy runbook — Azure Container Apps → Teams demo (Path C)

A copy-paste runbook that takes the backend from source to a **stable, machine-independent** Teams
demo: provision the backend as a cloud web service (Azure Container Apps), enable the agentic and
approval features, wire the Teams entry point, and run the three trials in Copilot Chat. Once
applied, your laptop can be off and the demo still works — the FQDN is fixed and the compute is in
Azure.

This is the production path. For a throwaway "does the pipeline work today" test, the dev-tunnel
path in [`deploy.md`](deploy.md) is faster; this runbook is for a real, repeatable demo.

> Conventions: run from the **repo root** unless noted. `terraform` commands run in `infra/`.
> Values flow between steps via `terraform output` — copy them as shown.

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
- **(Optional) Azure OpenAI** deployment (GPT-4o-class, accepts `max_tokens`) if you want the
  agentic roles live; **(optional)** a throwaway GitHub repo with `blocker`-labelled issues for the
  real-evidence Customer Promise trial.

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
```

Then `terraform apply` (Phase 1 step 3, or re-apply if you set these after the first apply).
`DRY_RUN_DEFAULT` stays true, so every write is predicted — the demo is safe.

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
> gated: the **Add** button stays disabled until the account is entitled. Either assign a Microsoft
> 365 Copilot license, or set up **pay-as-you-go**: in the Microsoft 365 admin center → **Copilot →
> Billing & usage**, create a billing policy (Azure subscription + resource group, scope it to the
> demo accounts, set a budget), then connect it to **Microsoft 365 Copilot Chat**. The billing
> subscription must be visible in the M365 tenant's directory. Entitlement can take up to ~2 hours to
> propagate. See [`pay-as-you-go/setup`](https://learn.microsoft.com/en-us/copilot/microsoft-365/pay-as-you-go/setup).

Single-flow (any signed-in user):

1. In Copilot Chat, invoke the agent and type a trial request, e.g.
   `promise Customer A that SSO is GA by 2026-06-17`.
2. The **Change Court card** renders: impact evidence, the refusal + safe alternative, required
   approvers, verdict buttons.
3. Click the verdict → `cast_verdict` resumes the run from its checkpoint and returns the result card.

Two-user separation of duties (needs Phase 2 `APPROVER_DIRECTORY` + a low-privilege requester
account; full script in [`two-user-demo.md`](two-user-demo.md)):

1. **Requester** (low-priv) submits the change → card holds at requester review → **Send for
   approval** with a note.
2. **Approver** (a different account in `APPROVER_DIRECTORY`) → pulls the queue → **Approve**.
3. Quorum satisfied → executes (DRY_RUN by default, ADR-0007) → audit recorded. Confirm the
   requester **cannot** approve their own change, and an account outside the directory cannot decide.

The three trials and their expected outcomes are in [`trials.md`](../reference/trials.md).

---

## Phase 6 — Verify, then idle or tear down

- **Health of the agentic path:** read the `court://metrics` MCP resource — the `agentic.*` fallback
  counters should be ~zero on healthy runs. Non-zero means the LLM path is failing and silently
  falling back (check the OpenAI endpoint/role/`max_tokens` support).
- **Idle cost:** with `min_replicas = 0` the app scales to zero between demos (cold start on first
  call); ACR Basic is the only standing cost (~a few USD/month). `min_replicas = 1` keeps it warm.
- **Retention:** schedule `python -m scripts.purge` (nightly) so finished trials' checkpoints are
  reclaimed; the audit log is permanent (ADR-0008).
- **Tear down everything:** `cd infra && terraform destroy`.

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

- **The activity-feed toast's "Open with Copilot" action is inert.** The notification deep link
  (`NOTIFY_LINK_URL`) targets the app, but a declarative agent has no in-Teams surface to land on,
  so the button does nothing. Workaround: the approver opens Copilot Chat and runs
  `list_pending_approvals`. Fix tracked in
  [#256](https://github.com/jieyao-MilestoneHub/m365-teams-smooth/issues/256) (bot surface with
  actionable cards).
- **An updated app package does not reach users until they remove and re-add the agent.** Copilot
  caches the installed manifest and the plugin's auth state; after a catalog update users may see
  stale tools or silent auth failures (MCP calls sent without a token, no sign-in prompt). Per user:
  remove the app, fully quit and reopen Teams, re-add it from "Built for your org", and complete the
  sign-in on the first tool call. Platform behaviour, not ours — see Microsoft's
  [Copilot extensibility known issues](https://learn.microsoft.com/en-us/microsoft-365/copilot/extensibility/known-issues).
  Never ship a package update on demo day.

---

## The machine question

Nothing in this runbook is tied to a specific machine. The backend runs in Azure (fixed FQDN); the
demo runs in the Teams client (cloud); the only "where" that matters is **a host with `az`/Terraform
access** to run Phase 1–4 — that can be any laptop, VM, or CI runner. After Phase 4, the demo is
fully cloud-resident.
