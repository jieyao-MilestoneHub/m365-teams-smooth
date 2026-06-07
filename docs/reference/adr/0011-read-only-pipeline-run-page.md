# ADR-0011: Read-only pipeline run page behind signed deep links

- **Status:** Accepted
- **Date:** 2026-06-07

## Context

The Adaptive Card is the court's decision surface, but it is phase-scoped: it shows the trial as
it stands at one gate, not the run as it unfolds. A reviewer auditing the agent's full courtroom
flow — node-by-node timing, the evidence and knowledge citations the Prosecutor gathered, the
quorum forming vote by vote, per-step execution effects, the audit record — had no surface at all;
the standing rule was "the card is the only UI, no web dashboard." Meanwhile the data already
existed or was cheap to make durable: the graph nodes are uniformly instrumented, the approval
ledger is event-sourced, and the trial record is checkpointed. Three decisions were needed: what
the inspection surface is allowed to do, how it is exposed and protected on a public origin, and
where its data comes from.

## Decision

1. **A read-only run page, served by the backend itself.** One static, self-contained HTML file
   under `api/` (`GET /runs/{thread_id}`), polling `GET /api/runs/{thread_id}/events` until the
   trial reaches a terminal status. It renders the pipeline as a CI-style run log — stage rail
   with the courtroom roles, a distinct verdict gate with live quorum progress, per-system
   execution lanes with before→after effects, and the audit footer. **It inspects, it never
   decides**: the page hosts no mutating action, and every verdict still happens on the card.
   This amends the "card is the only UI" rule to "the card is the only *decision* UI."
2. **Access is per-trial signed deep links, failing closed.** A pure-stdlib HMAC helper
   (`app/security/run_links.py`) signs `thread_id` into a short url-safe token; the card mints
   the link (`?t=…`) only when the composition root can. A missing or wrong token is 401; with no
   `RUN_LINK_SECRET` configured the surface 404s entirely — an unverifiable endpoint advertises
   nothing. The token is static per thread and carries no TTL: it grants read access to exactly
   one trial's run log, which is the same information the card recipients already hold. Page
   responses carry `Referrer-Policy: no-referrer` and `X-Robots-Tag: noindex` since the token
   travels in the URL. Full OAuth on this surface was rejected as demo-hostile and implementation
   risk for no added authority (there is nothing to escalate to).
3. **Progress data is an append-only run-event log; approval data is derived, not duplicated.**
   Nodes emit started/finished (and the execute node per-step) events through a `RunEventSink`
   port into a `run_events` table, committed per event so a concurrent poll observes the run
   mid-flight, across the verdict gap. Emission is best-effort — a failed write never fails a
   change. Approval actions are *not* re-emitted: the approval ledger remains their single home
   and `CourtService.get_run_view` folds both logs into one view at read time, so the page and
   the card can never disagree about who decided what.

## Consequences

- The full courtroom flow is auditable live and after the fact, from a link on the card — the
  pipeline is no longer a black box between submit and result.
- One new port (`RunEventSink`/`RunEventReader`), one append-only table, one REST router, one
  static file; `services/` stays the single business layer and `cards.py` stays a pure mapper
  (the link generator is injected at the composition edge).
- The run-event log lives in the same ephemeral SQLite as everything else: a new Container App
  revision wipes it, so run-page links die with their trials (covered by the demo-day checklist).
- Anyone holding a link can read that one trial's run log; link hygiene is the access model,
  by design. Rotating `RUN_LINK_SECRET` invalidates all previously minted links at once.
- An MCP `court://run/{thread_id}` resource over the same `get_run_view` is a one-call seam left
  open; it was skipped because the bearer-gated MCP surface does not serve the browser use case.
