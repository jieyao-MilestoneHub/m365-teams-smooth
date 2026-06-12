# ADR-0016: The LLM–deterministic allocation contract

- **Status:** Accepted (amends [ADR-0009](0009-agentic-roles-and-governed-autonomy.md))
- **Date:** 2026-06-12

## Context

The pipeline's agentic layer (validated LLM perception and planning with deterministic fallbacks)
originally wrapped only the five specialized scenarios, and three gaps undercut it as a general
engine: a request outside those scenarios received no agentic treatment at all; a change no rule
pack governed scored LOW and executed with no approver; and agentic evidence could not raise tags,
so a risk the model uncovered could never reach policy. The allocation between LLM and
deterministic logic was implicit — and in places it was an accident of the demo scenarios rather
than a principle.

## Decision: who owns what, on every path

**The LLM owns perception and plan content, on every path — never only on scripted ones:**

- **Classification** — an open kebab-case subject from the parser; the five specialized subjects
  are prompt hints, not a gate, and a novel parse (with its actions) is kept.
- **Perception** — the Prosecutor selects reads from the full registered read catalog (validated
  per read, capped), for specialized and novel subjects alike, and may flag evidence tags strictly
  from the registered vocabulary.
- **Plan content** — the Defender drafts the steps and rationale (validated per step against the
  capability registry; one invalid step rejects the whole draft), for specialized and novel
  subjects alike.

**Deterministic logic owns governance — the parts that must be reproducible and auditable:**

- Risk scoring, banding, quorum derivation, verdict options, and approval enforcement — all
  interpreted from rule-pack data.
- **Refusal authority**: a change is unsafe when a `marks_unsafe` tag fires; the plan kind is
  pinned by the baseline (the LLM cannot flip a refusal back to feasible); the generic baseline
  refuses outright when an unsafe tag fired and no specialized alternative exists.
- **The ungoverned floor**: a change no pack governs lands at MEDIUM with a manager quorum
  (ADR's of record: the `UNGOVERNED` fallback pack) — "unknown" means "ask a human".

**The bridge is additive-only.** LLM-proposed tags are accepted solely from the vocabulary the
rule packs themselves define; an accepted tag can raise risk, convene an approver, or trigger the
deterministic refusal — it can never lower risk, remove an approver, or unmark unsafe. Perception
may escalate; only deterministic rules decide. This supersedes ADR-0009's stronger "tags never
come from the LLM": the reproducibility that stance protected is preserved because scoring over
tags is unchanged and the vocabulary derives from the same pack data policy interprets.

**Offline mode is a verification fixture, not a product mode.** The deterministic parsers,
scenario gatherers/planners, and the offline LLM fake exist so the suite and the credential-free
reproduction stay green and reproducible; the product path runs with a real LLM provider. No
scenario hardcoding may be added to make a demo work — that trade is explicitly rejected.

## Consequences

- Any request — scripted or novel — flows through the same pipeline: LLM classification and
  perception, deterministic risk/quorum over validated signals, identity-bound approval.
- New scenarios extend the system as data (rule packs define matching, risk, quorum, and thereby
  the tag vocabulary) plus optional adapters; specialized gatherers/planners are an optimization,
  not a requirement.
- Offline, the five specialized scenarios behave exactly as before; the one intended difference
  is that off-script requests now wait for a manager instead of executing.
