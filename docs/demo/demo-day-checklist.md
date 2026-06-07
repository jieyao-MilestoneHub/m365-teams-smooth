# Demo-day prep — ordered checklist

Prep for running the trials live on the deployed environment (Azure Container Apps → Teams). The
full provisioning and sideload phases live in the [deploy runbook](../deploy/runbook.md) — this
list assumes they are done and covers only the day-of order.

The Container App's SQLite is **ephemeral: every new revision wipes all trials AND the bot's
conversation references**, so the deploy must come first and everything stateful after it.

1. **Pin the config** in `infra/terraform.tfvars`: `run_link_secret` (32+ random bytes, e.g.
   `openssl rand -base64 32`), plus the demo's run mode (`dry_run_default`, `integration_mode`).
2. **Build & push** the image (runbook Phase 1 step 2) and **`terraform apply`** — this rolls a
   new revision and wipes the DB; do it *before* any prep below.
3. **Freeze deploys.** Any later push/apply mid-demo = a new revision = lost trials, lost
   conversation references, dead run-page links.
4. **Reset demo data** that previous runs mutated — e.g. the rehearsal milestone's due date in the
   demo GitHub repo back to its pre-trial value:
   `gh api -X PATCH repos/<owner>/<repo>/milestones/<n> -f due_on=2026-06-10T00:00:00Z`.
5. **Re-register conversation references:** each participant (requester *and* approver) sends the
   bot one message — without this the proactive approval card cannot land and only the toast does.
6. **Warm the knowledge path:** run one throwaway query ~2 minutes before recording (the Azure AI
   Search data plane is slow on its first call after idle).
7. **Smoke:** `curl "$BASE/api/health"` → 200; submit a throwaway trial; open its card's
   **View pipeline run** link in a browser → the page renders and polls. A `404` on `/runs/...`
   means `run_link_secret` is unset on the live revision; a `401` means the token/URL is stale.
8. Run the three trials. Second screen = the run page; Teams = the decision surface.

## Operational notes

- **Health of the agentic path:** read the `court://metrics` MCP resource — the `agentic.*`
  fallback counters should be ~zero on healthy runs. Non-zero means the LLM path is failing and
  silently falling back (check the OpenAI endpoint/role/`max_tokens` support).
- **Idle cost:** with `min_replicas = 0` the app scales to zero between demos (cold start on first
  call); ACR Basic is the only standing cost (~a few USD/month). `min_replicas = 1` keeps it warm.
- **Retention:** schedule `python -m scripts.purge` (nightly) so finished trials' checkpoints are
  reclaimed; the audit log is permanent
  ([ADR-0008](../reference/adr/0008-context-and-storage-bounds.md)).
- **Tear down everything:** `cd infra && terraform destroy`.
