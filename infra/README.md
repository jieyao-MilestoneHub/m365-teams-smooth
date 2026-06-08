# infra/ — Terraform for the live Microsoft 365 deployment

Provisions everything needed to run the backend in a tenant and have the declarative agent call it:

- **Azure Container Apps** (Consumption) running the backend image, with HTTPS ingress on `/mcp`.
- **Azure Container Registry** (Basic) the app pulls from, plus a user-assigned identity with `AcrPull`.
- **Log Analytics** workspace for the Container Apps environment.
- **Entra ID app registration** exposing the `court.use` scope, with `api://<client-id>` as the
  audience the backend validates — wired straight into the app's `OAUTH_*` env.

The backend runs **fully mocked by default** (`force_all_mock = true`), so the live agent is a
reliable demo with no Microsoft Graph permissions required.

> **Costs are incurred only when you run `terraform apply`.** Writing/validating this code is free.
> See *Cost* below, and `terraform destroy` to remove everything.

The runtime resources and the app registration may live in **different tenants** (a common
enterprise topology): `azure_tenant_id` is the subscription's tenant for `azurerm`, while
`entra_tenant_id` is the M365 tenant users sign in to — it drives the `azuread` provider and the
OAuth issuer/JWKS the backend validates. Point both at the same tenant when you have only one.

Optionally, the `knowledge_*` variables wire knowledge grounding (Azure AI Search agentic
retrieval) into the app: the `KNOWLEDGE_*` env is injected only when set, and the app's managed
identity is granted the Search/OpenAI data-plane roles via the provided resource ids — keyless auth,
no secrets.

Two further optional surfaces, both off by default and modeled the same way (set the variables and
they ship with `apply`, leave them empty and the app simply omits the env):

- **Bot surface** (`create_bot`, `bot_app_*`) — an Azure Bot + Teams channel pointing at the
  backend's `/api/messages`, so the court card's buttons work natively in Teams.
- **Approval notifications** (`notify_mode`, `notify_teams_app_id`, `notify_link_url`) — best-effort
  decision toasts via the Microsoft Graph activity feed; delivery never blocks a trial.

> **`apply` is declarative and idempotent — keep `terraform.tfvars` complete.** Every secret and
> optional surface is conditional on its variable, so an `apply` with a value left blank *removes*
> that secret/env from the live app. Always re-apply from a tfvars that carries the full intended
> state (all secrets + any bot/notify/graph values you rely on). See *Updating vs reconciling* below.

## Prerequisites

- Terraform ≥ 1.5, Azure CLI logged in to the subscription's tenant (`az login --tenant <id>`),
  and Docker. The signed-in account needs rights to create resources in the subscription **and** an
  Entra app registration in the M365 tenant.

## Apply

```bash
cd infra
cp terraform.tfvars.example terraform.tfvars   # fill in subscription_id + both tenant ids
terraform init

# 1) Create the registry first so the image has somewhere to live.
terraform apply -target=azurerm_container_registry.this

# 2) Build and push the backend image to the new ACR.
ACR=$(terraform output -raw acr_login_server)
az acr login --name "${ACR%%.*}"
docker build -f ../backend/Dockerfile -t "$ACR/change-court:latest" ..
docker push "$ACR/change-court:latest"

# 3) Create everything else (Container App + Entra app).
terraform apply
```

## Updating vs reconciling

Two distinct situations, two safe paths — don't mix them:

- **Ship a new backend build to an instance Terraform owns.** Build/push a new image tag, set
  `image_tag`, and `terraform apply`. The single-responsibility revision roll is expected.
- **Update an instance that was tuned out-of-band** (env or secrets changed with `az` after the
  original apply — e.g. a quick config fix during a demo window). Terraform's state no longer
  reflects the live app, so a blind `apply` would revert those out-of-band changes. To push *only*
  a new image without disturbing them, swap it in place:

  ```bash
  az containerapp update -n changecourt -g changecourt-rg \
    --image "$(terraform -chdir=infra output -raw acr_login_server)/change-court:<new-tag>"
  ```

  To bring such an instance **back under full Terraform control**, reconcile deliberately (never
  mid-demo): copy every out-of-band value into `terraform.tfvars` (all secrets + any bot/notify
  env), `terraform import` any resources created with `az` (e.g. the Azure Bot), then review
  `terraform plan` until it shows no unintended removals before applying.

> Any `apply` rolls a new Container App revision, and the app's SQLite is **ephemeral** — a new
> revision wipes all trials and the bot's conversation references. Never apply during a demo window
> (see [`../docs/demo/demo-day-checklist.md`](../docs/demo/demo-day-checklist.md)).

## Wire up the agent

`terraform output` gives every value the next steps need:

```bash
terraform output public_base_url     # the backend origin (already baked into the running app)
terraform output mcp_server_url      # -> MCP_SERVER_URL    (m365 packaging)
terraform output mcp_host_domain     # -> MCP_HOST_DOMAIN   (m365 packaging)
terraform output entra_client_id
terraform output court_scope         # api://<client-id>/court.use
terraform output -raw entra_client_secret   # sensitive; for the Teams OAuth connection
```

1. **Register the Teams OAuth connection** (Teams Developer Portal → your app → *OAuth client
   registration*, or Agents Toolkit): use `entra_client_id`, the client secret, `court_scope`, and
   the tenant authorize/token endpoints. This yields the connection's reference id → `OAUTH_CONNECTION_ID`.
   *(This Teams-side connection is the one piece Terraform cannot create for you.)*
2. **Package and upload** the agent (from the repo root), supplying the placeholder values:

   ```bash
   TEAMS_APP_ID=$(uuidgen) \
   MCP_HOST_DOMAIN=$(terraform -chdir=infra output -raw mcp_host_domain) \
   MCP_SERVER_URL=$(terraform -chdir=infra output -raw mcp_server_url) \
   OAUTH_CONNECTION_ID=<from step 1> \
   make package
   ```

   Add `m365/color.png` (192×192) and `m365/outline.png` (32×32) first. Upload
   `m365/build/appPackage.zip` to the tenant (custom-app upload) and walk the three trials in
   Copilot Chat — ticking off the *Pending tenant* checks in [`../verify.md`](../verify.md).

See [`../docs/deploy/deploy.md`](../docs/deploy/deploy.md) for the conceptual walkthrough.

## Cost

Roughly, for a short-lived demo in a dev tenant (East US list prices; confirm in the pricing
calculator):

| Resource | Plan | Cost when idle | Notes |
| --- | --- | --- | --- |
| Container Apps | Consumption | ~$0 with `min_replicas = 0` (scales to zero) | Monthly free grant covers light demo traffic; cold start on first call. Set `min_replicas = 1` for a warm demo (~a few $/month while running). |
| Container Registry | Basic | ~$0.17/day (~$5/month) | The main standing cost; prorated. |
| Log Analytics | Pay-as-you-go | a few cents | Tiny ingestion for a demo. |
| Entra app registration | — | free | No charge. |

So expect **single-digit USD** for a demo window, dominated by ACR Basic. Run `terraform destroy`
when finished to stop all charges:

```bash
terraform destroy
```

State (`*.tfstate`) and `terraform.tfvars` are gitignored — they can contain secrets; never commit them.
