# Documentation map

Everything you need to understand, run, and deploy **AI Change Court**, organized into four areas.
Start with whichever matches your goal.

## How to read these docs

| Your goal | Start here |
| --- | --- |
| **Understand what this is & why** | [overview/goals.md](overview/goals.md) |
| **See how it's built** | [architecture/index.html](architecture/index.html) — open in a browser (offline) |
| **Run a demo / deploy it** | [deploy/runbook.md](deploy/runbook.md) (cloud → Teams) · [deploy/deploy.md](deploy/deploy.md) (concepts) |
| **Look up a specific contract or decision** | [reference/](reference/) |

New to the project? Read **overview → architecture diagram → reference/trials** in that order, then
the deploy guide when you're ready to run it.

## The four areas

### ① Overview — what & why
- [overview/goals.md](overview/goals.md) — the problem, the governed-autonomy thesis, the three
  trials, and scope discipline. **Read this first.**

### ② Architecture — how it's built
- [architecture/index.html](architecture/index.html) — six self-contained, offline diagram pages
  (one view per page, each with design rationale and guarantees): layered container architecture,
  the court pipeline + the agentic-vs-deterministic split, the separation-of-duties sequence, the
  trust/security boundaries, the persistence/data model, and the Microsoft platform integration
  map (Copilot · Azure AI Foundry / Foundry IQ · Graph · GitHub).

### ③ Deploy — running it, including environment setup
- [deploy/deploy.md](deploy/deploy.md) — the concepts: hosting over HTTPS, Entra ID OAuth2, the
  required environment variables, agentic + knowledge toggles, retention maintenance.
- [deploy/runbook.md](deploy/runbook.md) — copy-paste **Azure Container Apps → Teams** runbook for a
  stable, machine-independent demo (provision → enable features → sideload → run the trials).
- [deploy/two-user-demo.md](deploy/two-user-demo.md) — the separation-of-duties walkthrough
  (requester + approver), locally and in a tenant.
- [deploy/foundry-iq.md](deploy/foundry-iq.md) — optional knowledge grounding via Azure AI Search.
- [deploy/security.md](deploy/security.md) — security posture, trust boundaries, and the
  credential-rotation runbook.

### ④ Reference — contracts, schemas, decisions
- [reference/adr/](reference/adr/) — Architecture Decision Records: the significant, hard-to-reverse
  choices and their rationale (one file per decision).
- [reference/mcp-and-card-contract.md](reference/mcp-and-card-contract.md) — the MCP tool/resource
  and Adaptive Card data contract.
- [reference/domain-and-capability-schema.md](reference/domain-and-capability-schema.md) — the
  domain models and capability schema.
- [reference/policy-and-quorum.md](reference/policy-and-quorum.md) — how risk scoring and approver
  quorum are derived from rule-pack data.
- [reference/trials.md](reference/trials.md) — the three trials' inputs, fixtures, and expected
  results.

## Repo-level pointers

- [`../README.md`](../README.md) — project README (quick start, repo layout).
- [`../roadmap.md`](../roadmap.md) — phased plan.
- [`../verify.md`](../verify.md) — end-to-end verification checklist.
