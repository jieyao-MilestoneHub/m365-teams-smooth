# Security posture

How AI Change Court protects the systems it acts on, the decisions it records, and the credentials
it holds. This is the standing reference for a security review of a deployment.

## Trust boundaries

```
Caller (Copilot/Teams user)  ──OAuth2 bearer──▶  MCP server (resource server)
                                                    │  identity = verified token claims
                                                    ▼
                                                 CourtService  ──ports──▶  adapters ──▶ external APIs
                                                    │                         ▲
                                              append-only audit          param sanitizers
                                                                         (trust boundary)
```

Two boundaries do the load-bearing work:

1. **The MCP edge** authenticates every caller and turns the verified token into a `Principal`;
   nothing downstream trusts a caller-supplied identity.
2. **The adapter edge** is where LLM/planner-produced values first reach a real external API; every
   identifier is sanitized there before a URL is built.

## Authentication & authorization

- **OAuth 2.0 resource server.** The MCP server validates bearer tokens — signature, issuer,
  audience, and expiry (`app/mcp/security.py`). With `OAUTH_ISSUER` + `OAUTH_JWKS_URL` set it uses
  Entra ID JWKS (RS256); otherwise a local dev issuer (HS256) for offline development only.
  Algorithms are fixed per verifier, so RS256/HS256 confusion is not possible. The required scope
  is `court.use`.
- **Identity → Principal.** Claims map to a `Principal` (`oid`/`preferred_username`/`name`, standard
  OIDC); a caller cannot forge identity — it comes from the validated token, not the request body.
- **Separation of duties.** A requester can never approve their own change; identity comparison is
  on a normalized key (lowercased oid→upn→display_name), so casing tricks do not bypass it. A
  missing or empty identity is **denied** approver rights, never granted them. Approvers are
  resolved from the configured `ApproverDirectory` — the requester cannot choose their approver.

## Input handling & injection defense

- **Boundary validation.** A change request is rejected (not truncated) above `MAX_REQUEST_CHARS`
  (default 1000) and when blank — before any LLM or graph work (`CourtService.submit_change`).
- **Capability hallucination guard.** Every action the parser or planner produces is validated
  against the registered capability catalog; an unsupported action is rejected, recorded, and never
  planned or executed (`agent/nodes/intake.py`, the agentic planner/gatherer validation).
- **Parameter sanitization at the adapter boundary.** The capability guard checks that required
  keys exist, not their values — so a crafted `repo` or SharePoint `path` could otherwise traverse
  (`../`) to a resource the token can reach. `adapters/integrations/validation.py` (`safe_repo`,
  `safe_path`) rejects traversal and malformed identifiers before any API path is built. This is
  the correct defense: prompt-injection cannot be "sanitized" out of free text, so the system
  constrains the **output** (the API call), not the prompt.
- **No injection sinks.** All persistence is via SQLAlchemy (parameterized, no string SQL); no
  `eval`/`exec`/`pickle`/`yaml.load`; checkpoint state is JSON-only.

## Audit & data integrity

- **Append-only audit.** Audit records are keyed by a UUID primary key and only ever inserted —
  there is no update path. Before/after snapshots and rollback hints are *derived views*, stored
  once. The retention purge (`scripts.purge`) deletes only working storage (checkpoints, verdict
  claims, pending rows) — **never** audit records.
- **Idempotent verdicts.** A composite primary key `(thread_id, idempotency_key)` makes a repeated
  verdict a no-op that returns the recorded result; no double execution across REST and MCP.
- **Truthful terminal status.** Rejected/withdrawn trials are recorded as such (not a generic
  "done"), so the permanent record and the precedents derived from it cannot mislead.

## Resource bounds (DoS resistance)

Every reachable loop and allocation is bounded: request size (1000 chars), LLM output
(`LLM_MAX_TOKENS`=1024) and per-call timeout (30s), graph wall-clock guard (60s), agentic reads
(`MAX_AGENTIC_READS`=5), accumulated errors (50), and idempotency-aware retries (max 3, exponential
backoff). Queue and precedent reads scale with open work, not history (see `reference/adr/0008`).

## Secrets

- **Never in git.** `.env` is gitignored at the repo root (recursive `.env` pattern); only
  `.env.example` is committed. A `gitleaks` CI job scans every push and PR as the last line.
- **Never in logs or errors.** Logs carry identity keys and ids, never tokens/secrets; client-facing
  errors are typed and generic (full detail stays server-side).
- **Managed in deployment.** Terraform stores `GITHUB_TOKEN` / `GRAPH_CLIENT_SECRET` as Container
  App secrets (not plain env); keyless Azure dependencies authenticate as the managed identity
  (`AZURE_CLIENT_ID`).

### Credential rotation runbook

If a token/secret is ever exposed (committed, shared, logged), rotate immediately — exposure is
permanent regardless of later deletion:

- **`GITHUB_TOKEN`** — GitHub → Settings → Developer settings → Personal access tokens → revoke the
  token, issue a new fine-grained token scoped to the seed repo only, update the deployment secret.
- **`GRAPH_CLIENT_SECRET`** — Entra admin center → App registrations → the app → Certificates &
  secrets → delete the secret, add a new one, update the Container App secret.
- After rotating, confirm no copy remains in shell history, CI logs, or a local `.env` shared with
  others.

## Deployment hardening

- The container runs as a non-root user (uid 1000) and serves `app.asgi:app` (REST health + the
  OAuth2-protected MCP server). TLS is terminated by Container Apps ingress.
- The health endpoint exposes only `{status, version}` — no config or internals.

## Scope assumptions

Single-tenant per deployment: one Entra issuer, one database. Audit, precedents, and the verdict
ledger are scoped to the deployment, not partitioned by tenant. Multi-tenant isolation would be a
deliberate future change (a tenant key on the stores + queries), not an accident of the current
design.
