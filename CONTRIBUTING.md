# Contributing

Thanks for your interest in contributing to **AI Change Court**.

AI Change Court helps teams review and govern risky enterprise decisions before those decisions become real actions across Microsoft 365 and other work systems. A request moves through an inspectable court flow:

```text
intake → impact → options → policy + quorum → [verdict] → execute → audit
````

This guide explains how to set up the project, make changes, open pull requests, and keep contributions safe and easy to review.

## Table of contents

* [Code of conduct](#code-of-conduct)
* [Ways to contribute](#ways-to-contribute)
* [Before you start](#before-you-start)
* [Local development](#local-development)
* [Branch and commit conventions](#branch-and-commit-conventions)
* [Pull requests](#pull-requests)
* [Testing](#testing)
* [Safety expectations](#safety-expectations)
* [Documentation](#documentation)
* [Reporting bugs](#reporting-bugs)
* [Security](#security)

## Code of conduct

Please be respectful, constructive, and specific when opening issues, reviewing pull requests, or discussing design decisions.

Good contributions include not only code, but also clear bug reports, reproducible test cases, documentation improvements, design feedback, and safer defaults.

## Ways to contribute

You can help by contributing to:

* Backend services and FastAPI endpoints.
* MCP tools and resources.
* Microsoft 365 / Teams integration surfaces.
* Adaptive Cards and user-facing approval flows.
* Integration adapters such as GitHub, Outlook, Planner, SharePoint, Teams, CRM, or Entra.
* Policy, quorum, and risk-scoring logic.
* Court pipeline behavior, including intake, impact analysis, safe alternatives, verdict handling, execution, and audit.
* Tests, fixtures, verification scripts, and developer tooling.
* Documentation, architecture notes, ADRs, and setup guides.

If you are unsure where to start, look for issues labeled `good first issue`, `help wanted`, or `ready`.

## Before you start

1. Check existing issues and pull requests to avoid duplicate work.
2. Open an issue for larger changes before implementing them.
3. Keep changes focused and reviewable.
4. Use mock integrations for local development unless you intentionally need a real external service.
5. Never commit secrets, access tokens, tenant IDs, customer data, or private credentials.

## Local development

The project can run locally without a Microsoft 365 tenant by using mock integrations.

### Backend

```bash
cd backend
uv sync
cp ../.env.example ../.env
uv run uvicorn app.main:app --reload
```

To run the ASGI app with REST plus the OAuth2-protected MCP server:

```bash
uv run uvicorn app.asgi:app --reload
```

### Common commands

From the repository root:

```bash
make demo
scripts/verify.sh
make check
```

Typical quality checks include:

```bash
ruff check
mypy
pytest
```

Depending on the area you change, you may also need to run card-generation or playground-related commands such as:

```bash
make cards
make bot
```

## Configuration

Use `.env.example` as the reference for local configuration.

Common variables include:

* `DB_URL` — database URL, usually local SQLite in development.
* `INTEGRATION_MODE` — selects real or mock integrations per system.
* `FORCE_ALL_MOCK=true` — runs the project with mock integrations.
* `DRY_RUN_DEFAULT` — controls whether new changes default to dry-run mode.
* `GITHUB_TOKEN` / `GITHUB_REPO` — required only when using the real GitHub adapter.
* `OAUTH_*` — OAuth2 settings for the MCP server.
* `PUBLIC_BASE_URL` — public HTTPS base URL when hosting the MCP server.

Do not commit `.env` files or any private credentials.

## Branch and commit conventions

Create a short-lived branch from `main`:

```bash
git checkout main
git pull
git checkout -b <type>/<scope>
```

Recommended branch prefixes:

* `feat/<scope>` — new functionality.
* `fix/<scope>` — bug fix.
* `docs/<scope>` — documentation change.
* `test/<scope>` — tests or fixtures.
* `chore/<scope>` — tooling, dependencies, or configuration.
* `refactor/<scope>` — behavior-preserving refactor.

Examples:

```bash
feat/vendor-access-expiry
fix/verdict-idempotency
docs/mcp-setup
test/customer-promise-fixtures
chore/update-ci
```

Use Conventional Commits where possible:

```text
feat: add SharePoint permission adapter
fix: prevent duplicate verdict execution
docs: clarify local MCP setup
test: add policy quorum fixtures
chore: update verification script
refactor: isolate capability validation
```

Use imperative mood: `add`, `fix`, `update`, not `added`, `fixed`, or `updated`.

## Pull requests

A good pull request is small, focused, and easy to review.

Before opening a PR:

* Rebase or update your branch from `main`.
* Run relevant tests and checks.
* Update documentation if behavior, configuration, or public contracts changed.
* Make sure the PR description explains what changed, why it changed, and how it was tested.
* Link related issues with `Closes #123` or `Refs #123`.

PR description template:

````markdown
## Summary

Describe the change in a few sentences.

## Why

Explain the problem, goal, or issue this addresses.

## What changed

- Change 1
- Change 2
- Change 3

## How to test

```bash
scripts/verify.sh
make check
````

## Notes

Mention any mock behavior, real integration requirements, migration steps, or follow-up work.

````

A PR is ready to merge when:

1. CI passes.
2. At least one reviewer approves.
3. Review comments are resolved.
4. The change does not break local development, existing checks, or documented behavior.

Use squash merge when possible and delete the branch after merge.

## Testing

Please add or update tests when changing behavior.

Recommended test coverage:

- **Domain logic:** unit tests.
- **Court pipeline:** tests for intake, impact, options, policy/quorum, verdict, execution, and audit behavior.
- **Capability registry:** tests for supported and unsupported actions.
- **Policy and quorum:** deterministic tests for risk and approval outcomes.
- **Adapters:** mock tests, contract tests, and optional gated live tests.
- **MCP tools/resources:** integration tests.
- **Adaptive Cards:** generated fixture or snapshot checks where useful.
- **Safety regressions:** tests for dry-run behavior, verdict idempotency, unsupported action rejection, partial failure, and audit integrity.

Before opening a behavior-changing PR, run:

```bash
scripts/verify.sh
make check
````

If a check requires credentials, a tenant, or a real external service, mention that in the PR and explain what you verified locally.

## Safety expectations

AI Change Court controls actions that may affect real systems. Contributions must preserve these safety expectations.

### Capability validation

* Requested actions should map to registered capabilities.
* Unsupported actions should be rejected or handled as safe alternatives.
* The system should not invent hidden tools, unregistered writes, or implicit permissions.

### Dry-run behavior

* Dry-run mode must not mutate external systems.
* Dry-run results should still show predicted effects and rollback hints where possible.
* Real adapters should make dry-run behavior explicit.

### Verdict handling

* High-risk changes should wait for a verdict before execution.
* Execution should only continue after a valid approval path.
* Casting the same verdict more than once must not cause duplicate execution.

### Policy and quorum

* Risk scoring and required approvers should be deterministic and testable.
* LLMs may help summarize, draft, or reason about evidence, but policy enforcement should not depend on unreviewable model output alone.
* Changes to approval or quorum logic should include tests.

### Audit trail

* Important actions should produce audit records.
* Audit records should preserve before/after information where available.
* Partial failures should be visible and should include recovery or rollback hints when possible.

### External integrations

When changing or adding an integration adapter:

* Keep external reads and writes behind adapter interfaces.
* Gate real writes behind configuration.
* Prefer least-privilege credentials.
* Make operations idempotent where practical.
* Return structured errors.
* Document required permissions and side effects.
* Add mock or contract tests.

## Documentation

Update documentation when you change:

* Setup steps.
* Environment variables.
* Architecture.
* MCP tools or resources.
* Adapter behavior.
* Policy or quorum behavior.
* Trial/reference scenario behavior.
* Verification commands.
* Security or safety assumptions.

Use ADRs for durable architecture decisions.

Keep documentation clear about what runs locally, what uses mock integrations, and what requires real credentials or tenant access.

## Reporting bugs

When reporting a bug, include:

* What you tried to do.
* What you expected to happen.
* What actually happened.
* Steps to reproduce.
* Relevant logs or screenshots.
* Whether you used mock integrations, real integrations, or tenant-backed services.
* Your operating system and Python/package manager versions if relevant.

For safety-related bugs, mention whether the issue affects:

* unsupported action rejection
* dry-run mutation
* verdict bypass
* duplicate execution
* missing audit records
* incorrect approver or quorum resolution
* real external writes
* adapter permissions

## Security

Do not open public issues containing secrets, tokens, tenant IDs, customer data, private URLs, or exploitable security details.

If you discover a serious vulnerability, report it privately to the maintainer instead of posting details publicly.

## Questions

Open a GitHub issue or discussion if you need help with setup, architecture, contribution scope, or expected behavior.

Thank you for helping improve AI Change Court.