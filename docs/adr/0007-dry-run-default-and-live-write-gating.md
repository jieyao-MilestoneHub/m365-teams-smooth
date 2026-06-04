# ADR-0007: Dry-run stays the default; live writes are gated opt-in

- **Status:** Accepted
- **Date:** 2026-06-04

## Context

With approval routing enforced (ADR-0006), an approved trial *could* now flip from `DRY_RUN` to
real mutations. Live writes against Microsoft 365 systems require Graph **write** scopes
(`Calendars.ReadWrite`, `Sites.ReadWrite.All`, …) with admin consent, and they raise the blast
radius of any defect from "wrong prediction" to "wrong mutation in a tenant". The question is
whether, and under what conditions, execution should leave dry-run.

## Decision

1. **`DRY_RUN_DEFAULT=true` remains the default in every environment.** The execute node keeps
   returning predicted effects with no side effects unless a run is explicitly opted in. Dry-run
   stays a first-class state field, not a deployment mode.
2. **Live writes are deferred** until the approval surfaces (MCP tools, phase-aware card, bot) have
   been exercised in a real tenant. No code change is needed when that day comes — `run_mode` is
   already honored per run.
3. **Conditions to enable a live write**, all of them, when the deferral ends:
   - the trial passed the approval gates (a verdict alone is not enough — quorum must be satisfied
     where required);
   - the target system is explicitly opted in (`run_mode=live` on the submitted change, plus the
     per-system `INTEGRATION_MODE=<system>:real` and its credentials/scopes);
   - `FORCE_ALL_MOCK=true` stays available as the kill-switch that turns every integration back
     into a mock regardless of other settings.
4. **Blast-radius limits stay advisory-first:** rollback hints remain data the card shows, never
   auto-executed (ADR-0002 / the audit contract), and the append-only audit record is written for
   live runs exactly as for dry runs.

## Consequences

- Demos and CI remain deterministic and credential-free; nothing in the default path mutates an
  external system.
- Going live is a configuration decision per system and per run, reviewable in the audit trail,
  not a code branch — the dry-run/live split cannot drift into separate code paths.
- The kill-switch makes incident response trivial (one env var), at the cost of being coarse: it
  downgrades *all* systems, not one. A per-system kill override can be added later if needed.
