# ADR-0014 — Identity required for every approval action

## Status

Accepted (2026-06-12). Supersedes the identity-free fallback described as "backward compatible"
in [ADR-0006](0006-approval-routing-separation-of-duties.md) §7.

## Context

The court originally kept two approval paths. The identity-aware path (ADR-0006) enforced
separation of duties — requester ≠ approver, role authorization from `APPROVER_DIRECTORY`, an
event-sourced approval ledger. Alongside it, a *legacy single-verdict path* remained: submitting
without a requester ran the trial to the verdict gate, low-risk changes auto-approved the
moment they were submitted, and `cast_verdict` accepted an unauthenticated caller whenever no
directory was configured. The card rendered direct verdict buttons for that path.

The product runs inside real enterprise workflows — Microsoft Teams with Entra identities. There,
a gate that enforces separation of duties *only when configured* is not a gate: any surface that
can resume a trial without an identity is a bypass, and the audit trail records "reviewer" instead
of a person.

## Decision

There is one flow, and it is identity-bound end to end:

1. **`submit_change` requires the authenticated requester.** Every trial holds at the requester's
   own review gate (`awaiting_requester_review`). The exception-based model is unchanged: sending
   a no-approver change executes it on the requester's confirmation; quorum-bearing changes wait
   for their approvers.
2. **`cast_verdict` requires an authorized principal and a configured directory** — the same
   `authorize_caster` check as `decide` (requester cannot self-approve; the caster must hold a
   required quorum role) on every path. The internal low-risk auto-approve at submit time is gone;
   `approvals_configured()` (the fallback switch) is removed.
3. **Surfaces follow.** The trial card renders actions only at the two identity gates (requester
   review → `send_for_approval`/`withdraw_change`; approval → `decide`); the bot's identity-free
   verdict route is removed; MCP `submit_change`/`cast_verdict` require the OAuth principal.
4. **Credential-free verification keeps explicit identities.** The demo and card-export drivers
   (and the test suite) pass seed principals and a seed directory (`scripts/demo_identities.py`);
   mocked integrations remain a CI/dev concern, never an identity bypass.

## Consequences

- Separation of duties holds on every surface that can resume a trial; the audit trail always
  names real actors.
- `APPROVER_DIRECTORY` is required for any deployment whose changes convene approvers — without
  it a quorum-bearing trial can be submitted and sent but never decided. No-approver changes
  execute on the requester's confirmation either way.
- Unauthenticated MCP calls to `submit_change`/`cast_verdict` fail with the unauthorized error;
  callers must complete the OAuth2 flow (the declarative agent already does).
- The Playground bot still works tenant-free: its switchable users provide the two identities.
