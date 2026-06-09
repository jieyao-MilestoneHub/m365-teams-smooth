# AI Change Court

![CI](https://github.com/jieyao-MilestoneHub/m365-teams-smooth/actions/workflows/ci.yml/badge.svg)

**Governed execution for risky enterprise decisions in Microsoft Teams.**

Cross-system changes happen in chat faster than anyone can keep them consistent — "move the rehearsal
a week out", "post the weekly status report". Each touches GitHub, calendars, the task planner, and
Teams, and each is easy to half-do: one system updated, three left stale.

AI Change Court puts a change **on trial** before it acts: it gathers the cross-system impact, decides
who must sign off (no one for routine work — the requester's own confirmation is enough), collects a
verdict, then executes — leaving an append-only audit trail. Crucially, it can **refuse an unsafe
change and propose a safer one**. Not a chatbot, not a workflow macro.

Every request runs through one inspectable pipeline —
`intake → impact → options → policy+quorum → [verdict] → execute → verify → audit` — built on
LangGraph behind a Microsoft 365 declarative agent. Each integration is pluggable: real or mock,
chosen per system in config. See the [architecture diagrams](docs/architecture/index.html) for how
it's built.

## Quick start — reproduce the demo

Runs **fully locally, credential-free** — every integration mocked, dry-run by default, no Microsoft
365 tenant. Needs Python 3.11+ with [`uv`](https://docs.astral.sh/uv/).

```bash
cd backend
uv sync
cp ../.env.example ../.env

make demo     # run the Informed Approval scenario end to end
make check    # ruff + mypy + pytest
```

**See the Change Court card** without a tenant: run the [Playground bot](m365/playground-bot/)
(`make bot`), or `make cards` and open a file from `m365/adaptive-cards/generated/` in the
[Adaptive Cards Designer](https://adaptivecards.io/designer). Full walkthrough →
[`docs/demo/`](docs/demo/README.md). Serve the API locally with
`uv run uvicorn app.asgi:app --reload` (REST + the OAuth2-protected MCP server at `/mcp`).

## Use it in your own environment

- **Real GitHub (opt-in).** Point the GitHub adapter at a throwaway repo with a `Launch Rehearsal`
  milestone; everything else stays mocked:

  ```bash
  INTEGRATION_MODE=github:real GITHUB_TOKEN=<token> GITHUB_REPO=<owner/name> make demo
  ```

- **Extend it.** A new integration is one adapter + one registration; a new scenario is one rule pack
  + gatherer + planner. The graph, services, REST, and MCP stay untouched.
- **Go live in Microsoft 365.** Host the backend over public HTTPS (e.g. Azure Container Apps),
  configure Entra ID OAuth2, and sideload the declarative agent in [`m365/`](m365/).

Configuration is env-driven — see [`.env.example`](.env.example) (key switches: `FORCE_ALL_MOCK`,
`INTEGRATION_MODE`, `DRY_RUN_DEFAULT`, `DB_URL`). Never commit secrets.

## Repository layout

```
backend/   FastAPI app: agent/ mcp/ api/ services/ ports/ adapters/ domain/
m365/      declarative agent manifest, plugin manifest, Adaptive Card templates
docs/      architecture diagrams, the demo, and ADRs
scripts/   developer/demo scripts (verify.sh, seed data)
```

## More

- **Architecture & design decisions** → [`docs/`](docs/README.md)
- **Contributing** → [`CONTRIBUTING.md`](CONTRIBUTING.md)
