# Contributing

Thanks for your interest in **AI Change Court** — it governs risky enterprise decisions before they
become real actions across Microsoft 365 and other systems, via an inspectable court flow:

```text
intake → impact → options → policy + quorum → [verdict] → execute → verify → audit
```

Good contributions include code, clear bug reports, reproducible tests, docs, design feedback, and
safer defaults. Be respectful, constructive, and specific. If unsure where to start, look for issues
labeled `good first issue`, `help wanted`, or `ready`.

## Before you start
1. Check existing issues/PRs to avoid duplicate work; open an issue for larger changes first.
2. Keep changes focused and reviewable (one responsibility per PR).
3. Use mock integrations locally unless you intentionally need a real service.
4. **Never commit secrets, tokens, tenant IDs, customer data, or credentials.**

## Local development
Runs fully locally with mock integrations — no Microsoft 365 tenant required.

```bash
cd backend
uv sync
cp ../.env.example ../.env
uv run uvicorn app.main:app --reload    # REST only: health + the read-only run page
uv run uvicorn app.asgi:app --reload    # + the bot endpoint and the OAuth2-protected MCP server at /mcp
```

From the repo root: `make demo` (trials end-to-end), `scripts/verify.sh` (trials + safety + MCP +
quality gates), `make check` (ruff + mypy + pytest). Card/playground work also uses `make cards` /
`make bot`. Configuration is env-driven — see [`.env.example`](.env.example); never commit `.env`.

## Branches and commits
Short-lived branch off `main`: `git checkout -b <type>/<scope>` where `<type>` is
`feat | fix | docs | test | chore | refactor` (e.g. `feat/vendor-access-expiry`). Use Conventional
Commits in the imperative mood:

```text
feat: add SharePoint permission adapter
fix: prevent duplicate verdict execution
docs: clarify local MCP setup
```

## Pull requests
Small, focused, easy to review. Before opening: update from `main`, run the relevant tests/checks,
update docs if behavior/config/contracts changed, and link issues (`Closes #123`). Describe **what**
changed, **why**, and **how you tested** it (the `## What / ## Why / ## How to test / ## Scope`
template). Ready to merge when CI passes, one reviewer approves, comments are resolved, and local dev
still works. **Squash-merge**, then delete the branch.

## Testing
Add or update tests when changing behavior. Cover: domain logic (unit); each court node (intake →
audit); the capability registry (supported **and** unsupported actions); policy/quorum (deterministic
risk + approver outcomes); adapters (mock + contract tests, live tests gated); MCP tools/resources;
Adaptive Cards (fixture/snapshot where useful); and **safety regressions** — dry-run, verdict
idempotency, unsupported-action rejection, partial failure, audit integrity. Run `scripts/verify.sh`
and `make check` before a behavior-changing PR; if a check needs credentials/a tenant, say so in the
PR and explain what you verified locally.

## Safety expectations
AI Change Court controls actions that may affect real systems — contributions must preserve these:

- **Capability validation** — requested actions map to registered capabilities; unsupported ones are
  rejected or turned into safe alternatives; no hidden tools, unregistered writes, or implicit
  permissions.
- **Dry-run** — must not mutate external systems; still shows predicted effects + rollback hints;
  real adapters make dry-run explicit.
- **Verdict handling** — high-risk changes wait for a verdict; execution only after a valid approval
  path; re-casting the same verdict never double-executes.
- **Policy and quorum** — risk scoring and required approvers are deterministic and testable; LLMs may
  summarize/draft/reason, but enforcement must not rest on unreviewable model output; changes here
  ship with tests.
- **Audit** — important actions produce append-only before/after records; partial failures are
  visible with recovery/rollback hints.
- **Integrations** — keep reads/writes behind adapter interfaces; gate real writes behind config;
  least-privilege credentials; idempotent where practical; structured errors; document required
  permissions and side effects; add mock/contract tests.

## Documentation
Update docs when you change setup, env vars, architecture, MCP tools/resources, adapter/policy/quorum
behavior, trial scenarios, verification commands, or security/safety assumptions. Use ADRs
(`docs/adr/`) for durable architecture decisions, and keep clear what runs locally vs. mocked
vs. tenant-backed.

## Reporting bugs & security
For bugs, include: what you tried, expected vs. actual, repro steps, logs/screenshots, whether you
used mock/real/tenant integrations, and OS/version if relevant. For safety bugs, note which guarantee
is affected (unsupported-action rejection, dry-run mutation, verdict bypass, duplicate execution,
missing audit, wrong quorum, real external writes, adapter permissions).

**Security:** never put secrets, tokens, tenant IDs, customer data, or exploitable details in public
issues. Report serious vulnerabilities privately to the maintainer. Questions: open a GitHub issue or
discussion.

Thank you for helping improve AI Change Court.
