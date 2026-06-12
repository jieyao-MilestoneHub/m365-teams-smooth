# AI Change Court

![CI](https://github.com/jieyao-MilestoneHub/m365-teams-smooth/actions/workflows/ci.yml/badge.svg)

**Cross-system impact evidence before a change executes — and a human approval gate that only
fires when the evidence demands it.**

Cross-system changes happen in chat faster than anyone can keep them consistent — "move the rehearsal
a week out", "post the weekly status report". Each touches GitHub, calendars, the task planner, and
Teams, and each is easy to half-do: one system updated, three left stale. The usual fix — route
everything through one more approval step — adds a queue in front of the same blind decision and
slows the routine work that never needed sign-off.

AI Change Court takes the opposite bet: **every change gets the same automatic impact analysis;
almost no change gets an extra approver.** Routine, low-risk requests auto-proceed on the
requester's own confirmation — zero approvers added, and the card says so. A human quorum convenes
only as the exception, when the cross-system evidence shows real risk (a contractual SLA, a release
freeze, a dependent milestone) — and that approver decides from the assembled evidence chain, not
from a title and a hunch. When a request is unsafe as posed, the court **refuses it and proposes a
safer alternative**. Everything — evidence, verdict, before/after — lands in an append-only audit
trail.

What that buys a team, concretely:

- **Fewer half-done changes** — one request updates every affected system, or none.
- **Fewer latent breaches reaching execution** — conflicts no single screen shows are caught and
  refused, with a safer date or scope already proposed.
- **Faster informed sign-off** — the rare approver starts from the evidence packet, not an
  investigation; the routine majority never waits on anyone.

Every request runs through one inspectable pipeline —
`intake → impact → options → policy+quorum → [verdict] → execute → verify → audit` — the courtroom
names are the pipeline's roles (the Prosecutor gathers impact, the Defender drafts the plan or the
safer alternative, the Clerk keeps the audit), not an extra layer of bureaucracy. Built on LangGraph
behind a Microsoft 365 declarative agent; each integration is pluggable, real or mock, per system.
See the [architecture diagrams](docs/architecture/index.html) for how it's built.

## When does it ask a human?

Approval routing is data, not code. Each change subject has a **rule pack**
([`backend/app/agent/policy_rules/packs.py`](backend/app/agent/policy_rules/packs.py)) mapping
evidence tags to risk weights and approver roles:

- **Low risk → no approver.** The requester's own confirmation executes the change.
  Internal-authority subjects — meeting action items, the weekly status report — declare an empty
  approver list outright: the pipeline still gathers evidence and writes the audit trail, but no
  one else is asked.
- **Specific evidence pulls in the role that owns that risk.** A milestone move adds the
  engineering lead; a pending announcement adds comms; a derived contractual-breach risk adds the
  account owner. No tag, no approver.
- **Separation of duties is enforced**, not assumed: every action — submit, confirm, decide —
  carries an authenticated identity
  ([ADR-0014](docs/adr/0014-identity-required-approvals.md)); when a quorum is required, the
  requester cannot approve their own change, and approvals are an append-only event ledger
  ([ADR-0006](docs/adr/0006-approval-routing-separation-of-duties.md)).
- **Risk scoring and quorum derivation are deterministic on purpose** — the same evidence always
  asks the same people ([ADR-0009](docs/adr/0009-agentic-roles-and-governed-autonomy.md)).

The full model — risk bands, the shipped rule packs, what auto-approves and why — is in
[docs/approval-policy.md](docs/approval-policy.md).

## Where it fits your existing process

If your changes already flow through a ticket with review, notification, and audit, Change Court
does not add a second approval board — it supplies the evidence your existing approval is missing:

- **Analysis-only pre-check.** Submit with `run_mode="analyze"`: the impact pipeline runs and
  stops — the evidence, the would-be plan, the risk level, and the would-be approvers, with nothing
  executed. A pre-ticket answer to "what would this break?".
- **Evidence into your ticket.** Set `EVIDENCE_WEBHOOK_URL` and each approval event POSTs the
  evidence packet — findings with citations, risk factors, the plan or safer alternative, the
  run-page link — to your ITSM or ticketing endpoint, so the approver you already have approves
  informed.
- **Quorum only for exceptions.** If you let it execute, the built-in gate stays exception-based:
  routine changes proceed on the requester's confirmation; named roles are convened only by the
  specific risk evidence that concerns them.

## Quick start — reproduce the demo

Runs **fully locally, credential-free** — every integration mocked, dry-run by default, no Microsoft
365 tenant. Needs Python 3.11+ with [`uv`](https://docs.astral.sh/uv/).

```bash
cp .env.example .env

make sync     # provision the backend virtualenv (uv)
make demo     # run the Informed Approval scenario end to end (the one recorded scenario)
make demo-all # also tour the additional capabilities the same engine handles (not recorded)
make check    # ruff + mypy + pytest
```

Prefer Docker? `make compose-up` runs the backend fully mocked, no local Python needed.

Informed Approval is the headline. The same engine also handles **Meeting Actions**, **Weekly
Report**, **Customer Promise**, and **Vendor Access** — wired and tested, runnable via `make
demo-all`, but not part of the recorded demo.

**See the Change Court card** without a tenant: run the [Playground bot](m365/playground-bot/)
(`make bot`), or `make cards` and open a file from `m365/adaptive-cards/generated/` in the
[Adaptive Cards Designer](https://adaptivecards.io/designer). Full walkthrough →
[`docs/demo/`](docs/demo/README.md). Serve the API locally with
`cd backend && uv run uvicorn app.asgi:app --reload` (REST + the bot endpoint + the OAuth2-protected
MCP server at `/mcp`).

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
backend/   FastAPI app: agent/ mcp/ api/ bot/ services/ ports/ adapters/ domain/
           observability/ security/
m365/      declarative agent manifest, plugin manifest, Adaptive Cards, Playground bot
docs/      architecture diagrams, the demo, and ADRs
scripts/   the end-to-end gate (verify.sh)
infra/     Terraform for live hosting: Azure Container Apps + the Entra app registration
```

`docker-compose.yml` runs the backend in Docker, fully mocked (`make compose-up`).

## More

- **Architecture & design decisions** → [`docs/`](docs/README.md)
- **Contributing** → [`CONTRIBUTING.md`](CONTRIBUTING.md)
