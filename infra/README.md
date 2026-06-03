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

## Prerequisites

- Terraform ≥ 1.5, Azure CLI logged in to the **dedicated M365 dev tenant** (`az login --tenant <id>`),
  and Docker. The signed-in account needs rights to create resources **and** an Entra app
  registration in that tenant.

## Apply

```bash
cd infra
cp terraform.tfvars.example terraform.tfvars   # fill in subscription_id + tenant_id
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

See [`../docs/deploy.md`](../docs/deploy.md) for the conceptual walkthrough.

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
