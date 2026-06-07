# The demo — what it shows, why it exists, and where it goes from here

This folder is the home of everything demo-related: what the demonstration proves, how to
reproduce every screen of it ([reproduce.md](reproduce.md)), the two-user approval walkthrough
([two-user-demo.md](two-user-demo.md)), and the ordered prep list for running it live on a
deployed environment ([demo-day-checklist.md](demo-day-checklist.md)).

## Why this exists

Everyday decisions are made in chat faster than governance can keep up — "move the rehearsal",
"create the action items", "post the weekly report", "promise the customer the feature". Each one
quietly touches GitHub, calendars, task boards, channels, CRM. By the time anyone reviews the
decision, the action has already happened, scattered across systems with no record of who agreed
to what.

AI Change Court puts the decision **on trial before it becomes action**: gather the cross-system
impact evidence, draft a feasible plan — or refuse and propose a safer alternative — resolve who
must approve, collect the verdict, execute, and keep an append-only audit. The differentiator is
the refusal: the court doesn't just ask *how* to do something, it asks **whether it should be done
at all** — and when the answer is no, it offers the safe path instead of a dead end.

## What the demo shows

The demo spine is three everyday chores, each put on trial in Microsoft 365 Copilot Chat / Teams
(golden expectations in [reference/trials.md](../reference/trials.md)):

| Trial | Request | What it proves |
| --- | --- | --- |
| **Reschedule Sync** | "move the rehearsal to 2026-06-17" | One sentence ripples four systems (milestone, calendar, tasks, announcement); HIGH risk derives a two-role quorum; an injected "also delete the old repo" is **blocked** by the capability guard. |
| — conflict variant | "move the rehearsal to 2026-06-16" | The target date collides with a seeded review → **refused as posed**, and the next free day is proposed as a safe alternative (no plain approve offered). |
| **Meeting Actions** | "create action items from standup" | Spoken follow-ups become owned, dated tasks; LOW risk → no approver — the requester's own confirmation executes. Governance proportional to risk. |
| **Weekly Report** | "post the Project X weekly report" | Cross-system activity collected once and posted as a report; with real GitHub configured, the evidence is the repository's actual week. |

Two earlier governance trials — the unsafe customer promise (refusal + private-preview
alternative) and over-broad vendor access (least-privilege + auto-revoke) — remain wired and
tested as additional court capabilities beyond the demo spine.

Every demo runs through the same surfaces: the **Change Court Adaptive Card** (the decision UI),
the **read-only pipeline run page** on a second screen (signed links, CI-style stage rail), and
the append-only audit at the end.

## Why it matters — the potential

- **The pattern generalizes.** Anything that mutates systems on someone's say-so — access grants,
  config changes, schedule moves, announcements, spend — fits the same trial shape. A new scenario
  is one rule pack + one gatherer + one planner ([integrate/new-scenario.md](../integrate/new-scenario.md));
  a new system is one adapter + one registration ([integrate/third-party-adapter.md](../integrate/third-party-adapter.md)).
- **Refusal with an alternative is the missing primitive.** Automation that can only comply is
  dangerous; automation that can only block is ignored. Proposing the safer path is what makes
  governance something people accept.
- **The audit is the product for the enterprise.** Every trial leaves evidence, approvers,
  verdict, before/after, and rollback hints in an append-only record — the artifact compliance
  actually asks for.

## How it's technically realized

High level only — the six architecture views carry the detail
([architecture/index.html](../architecture/index.html)):

- One LangGraph **court pipeline** with courtroom roles; the agent's freedom lives in perception
  and generation, while risk, quorum, refusal, and execution gating stay deterministic
  ([view ②](../architecture/02-court-pipeline.html)).
- The **verdict is a durable interrupt** — submit returns immediately, the run resumes from its
  checkpoint when a human decides, and a repeated verdict can never execute twice
  ([view ③](../architecture/03-approval-sequence.html)).
- **Microsoft platform integration**: Copilot/Teams entry, Azure AI Foundry for reasoning and
  Foundry IQ knowledge grounding (keyless), Microsoft Graph and GitHub for evidence and execution
  ([view ⑥](../architecture/06-platform-integration.html)).
- **Dry-run by default**, real-vs-mock per system from configuration, and a kill-switch that runs
  the entire pipeline with zero external credentials — which is exactly what makes the demo
  reproducible on any laptop ([ADR-0007](../reference/adr/0007-dry-run-default-and-live-write-gating.md)).

## How it extends and stays maintainable

The extension seams are documented goal-by-goal in [integrate/](../integrate/README.md). The
properties that keep maintenance honest: ports-and-adapters layering (the core never imports an
SDK), rules as data (scenarios don't add code to the policy node), golden trial expectations
enforced by tests, an append-only audit with a retention policy that reclaims working storage but
never the record ([ADR-0008](../reference/adr/0008-context-and-storage-bounds.md)), and a
verification gate (`scripts/verify.sh`) that must be green before any demo
([../../verify.md](../../verify.md)).

## Where to go

- **Reproduce every screen, credential-free** → [reproduce.md](reproduce.md)
- **Run the two-user approval flow** → [two-user-demo.md](two-user-demo.md)
- **Prep a live, deployed demo** → [demo-day-checklist.md](demo-day-checklist.md) +
  the [deploy runbook](../deploy/runbook.md)
