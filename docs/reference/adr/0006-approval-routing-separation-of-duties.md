# ADR-0006: Approval routing and separation of duties

- **Status:** Accepted
- **Date:** 2026-06-03

## Context

The Change Court card rendered only in the requester's own chat, `required_approvers` were roles with
no identity, and `cast_verdict` accepted any `actor` with no enforcement — so a requester could approve
their own risky change, defeating the quorum premise. We need real separation of duties, plus a
requester **self-review** gate so approvers aren't flooded with low-quality requests. A demo with two
real identities (a low-privilege requester; an approver) must be possible.

## Decision

1. **Two-gate workflow over the single existing interrupt.** The graph still suspends once
   (`interrupt_before=["execute"]`). While suspended, the *requester* acts (`send_for_approval` with a
   mandatory note, or `withdraw`) and only an authorized *approver* (`decide`: approve, or reject with a
   mandatory note) resumes into `execute`. No new graph nodes — the gates are service/state transitions.
2. **Event-sourced approvals.** Every action is an append-only `ApprovalEvent` in an `ApprovalLedger`
   port (alongside the audit repository and verdict ledger). A pure `evaluate_quorum` folds the events
   into `pending | satisfied | rejected | withdrawn`, and a pure `authorize_caster` enforces
   *requester ≠ approver* and role authorization. These pure functions are the single tested home for
   the rules, and make `all`/`any` multi-approver quorum real with no graph change.
3. **Identity at the edge, not the domain.** A `Principal` (oid/upn) flows in from the MCP token (or the
   bot) at submit and at each decision; the domain and service stay framework-agnostic. Identity is
   compared by a stable key (oid preferred).
4. **Roles → identities via config.** An env-driven `ApproverDirectory` (`approver_directory`) maps a
   required role to identities. The **requester cannot choose their approver** — the role comes from
   policy, the identity from config. A `ports/` seam can later swap in Microsoft Graph group resolution.
5. **Pull-based delivery.** `list_pending_approvals(principal)` returns the trials an approver may
   decide; no proactive bot/channel is required for the first cut.
6. **Every terminal outcome is audited.** Approve executes (honoring DRY_RUN); reject and withdraw also
   resume so the append-only trail records the outcome, then the precise `REJECTED`/`WITHDRAWN` status is
   set.
7. **Backward compatible.** Enforcement engages only when a requester identity *and* a configured
   directory are present; the legacy single-verdict path (and auto-approval of no-approval changes) is
   unchanged.

## Consequences

- Separation of duties is real and centrally tested (the requester can no longer self-approve; an
  unauthorized caster is rejected; rejection/sending require a note).
- Multi-approver quorum (`all`/`any`) is supported by the event fold without touching the graph.
- The MCP edge must read the authenticated caller and expose `send_for_approval` / `withdraw` /
  `decide` / `list_pending_approvals`; the card becomes phase-aware (requester actions vs approver
  actions). That surface wiring is the follow-up to this service-layer change.
- A true two-identity demo requires the real Copilot/Teams tenant (the Playground has one local
  identity); the logic is verified locally first via the service tests.
