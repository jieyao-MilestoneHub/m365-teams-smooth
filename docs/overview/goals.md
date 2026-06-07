# Project goals — what AI Change Court is and why

## The problem

Risky decisions are made in chat faster than governance can keep up — "delay the launch a week",
"promise this customer the feature by Friday", "give this vendor access until the campaign is done".
Each quietly mutates GitHub, calendars, CRM, SharePoint, support, and compliance. By the time anyone
reviews it, the action has already happened.

## What it is

AI Change Court puts a risky decision **on trial before it becomes action**. A request runs through
one inspectable pipeline:

```
intake → impact → options → policy + quorum → [verdict] → execute → verify → audit
```

It gathers cross-system impact evidence, produces a feasible plan **or refuses and proposes a safer
alternative**, resolves which stakeholders must approve, collects a verdict, executes, checks the
result against intent, and keeps an append-only audit trail. It is not a chatbot and not a workflow
macro.

## The thesis: governed autonomy

The differentiator is the refusal. Most automation asks "how do I do this?"; AI Change Court asks
"**should this be done, and is it even safe?**" — and when it is not, it says so and offers the safe
path. The agent's freedom lives in **perception and generation** (which evidence to gather, what
plan to draft); the **safety verdict stays deterministic** (risk scoring, quorum, refusal authority
are rules, not LLM output). See [the architecture views](../architecture/index.html) and
[ADR-0009](../reference/adr/0009-agentic-roles-and-governed-autonomy.md).

## What "done" looks like — the three trials

Every change must serve one of three demonstrable trials (details in
[reference/trials.md](../reference/trials.md)):

| Trial | Request | Outcome |
| --- | --- | --- |
| **Launch Slip** | slip the launch from June 10 to June 17 | Feasible, HIGH risk; ripples into calendar/planner/announcement; an unsupported "delete the repo" is blocked. |
| **Customer Promise** | promise Customer A that SSO is GA by June 17 | **Refused** — blockers + a security review *after* the date → private preview now, GA after the review. |
| **Vendor Access** | give the vendor access until the campaign is done | Ambiguous + over-broad → **least-privilege**, time-boxed, auto-revoke. |

## Scope discipline

One real integration (GitHub); the other six systems are realistic mocks, so the whole system runs
locally with zero credentials. Only the adapters the three trials need are built — no breadth for
breadth's sake. New work must converge on one of the three trials.

## Where to go next

- **Understand the design** → [architecture views](../architecture/index.html).
- **Run it / deploy it** → [deploy guide](../deploy/deploy.md) and the
  [Container Apps → Teams runbook](../deploy/runbook.md).
- **Dive into specifics** → [reference/](../reference/) (contracts, schemas, ADRs, trials).
