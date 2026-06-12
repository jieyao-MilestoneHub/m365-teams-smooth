# Approval policy — when does it ask a human?

The gate is **exception-based**: every change gets the same automatic cross-system impact
analysis; almost no change gets an extra approver. Routine, low-risk requests proceed on the
requester's own confirmation — zero approvers added, and the card states it
("Approval required: none — the requester's confirmation executes it."). A human quorum convenes
only when the gathered evidence shows real risk, and then it convenes exactly the roles that own
that risk. The gate's job is to *not* fire for routine work.

## Risk bands

Risk is a deterministic sum of weighted **evidence tags** — machine-readable facts the impact
phase derived from reading the affected systems. Tags are produced by adapter reads and
deterministic checks, never by the LLM (see
[ADR-0009](adr/0009-agentic-roles-and-governed-autonomy.md)): the same evidence always produces
the same score, the same level, and the same approvers.

| Band | Score | Consequence |
| --- | --- | --- |
| **low** | < 30 | No approval required — the requester's confirmation executes the change |
| **medium** | ≥ 30 | Approval required from the tag-derived roles |
| **high** | ≥ 60 | Approval required; unsafe-marking tags also force a refusal with a safer alternative |

## Rules are data, not code

Each change subject is governed by a **rule pack**
([`backend/app/agent/policy_rules/packs.py`](../backend/app/agent/policy_rules/packs.py)) — a
validated data literal mapping evidence tags to risk weights and approver roles. The engine
interprets the packs; changing policy means changing data.

| Pack | Fires on | Approvers | Routine path |
| --- | --- | --- | --- |
| `launch_slip` | milestone moves; calendar conflicts; latent contractual/freeze/dependency breaches | eng_lead ← `schedule.milestone_move` · comms ← `comms.pending_announcement` · account_owner ← `schedule.contractual_breach_risk` (policy: any) | a clean date move scores low |
| `customer_promise` | promised dates vs. security reviews, blocking issues, renewal risk | security_lead ← `security.review_after_due_date` · account_owner ← `crm.renewal_at_risk` | — |
| `vendor_access` | folder permission grants with overbroad scope / unclear duration | manager ← `access.overbroad_scope` · security_lead ← `data.customer_data_present` | a scoped, time-boxed grant scores low |
| `meeting_actions` | turning meeting follow-ups into tracked tasks | **none — empty approver list** | always the requester's own authority |
| `weekly_report` | posting an internal status summary | **none — empty approver list** | always the requester's own authority |

The two **empty-approver packs** are the policy stating, in data, that internal task tracking and
status reporting carry the requester's own authority: the pipeline still gathers the evidence and
writes the audit record, but no one else is asked and nothing waits in a queue.

## What auto-approves, and why

Every trial is identity-bound: the authenticated requester submits, and the trial pauses once at
the requester's *own* review gate — self-confirmation, not an approval layer
([ADR-0014](adr/0014-identity-required-approvals.md)). When the trial's risk lands in the **low**
band, sending it executes it right there, on the requester's confirmation; the trial record shows
exactly what was read and written. No second person is involved unless an evidence tag pulled one
in — but every action, including the routine ones, carries a real identity into the audit trail.

Approvers are derived **per tag, not per request**: a milestone move adds the engineering lead; a
pending announcement adds comms; a derived contractual-breach risk adds the account owner. No tag,
no approver.

## When a quorum does fire

Separation of duties is enforced, not assumed
([ADR-0006](adr/0006-approval-routing-separation-of-duties.md)):

- the requester cannot approve their own change;
- every approval action is an append-only event in an approval ledger — the decision history is
  replayable, not a mutable flag;
- roles map to real identities via the `APPROVER_DIRECTORY` configuration, and a pack's quorum
  policy (`all` / `any`) decides how many of the required roles must sign off.

What stays deterministic, on purpose: risk scoring, quorum derivation, verdict options, approval
enforcement, and refusal authority. Governance must be reproducible and auditable — that is the
substance of the design, not a limitation
([ADR-0009](adr/0009-agentic-roles-and-governed-autonomy.md)).

## Plugging into an existing process

If your changes already flow through a ticket with its own review, the gate composes instead of
competing:

- **Analysis-only mode** (`run_mode="analyze"`) runs the impact pipeline and stops — the evidence,
  the would-be plan, the risk level, and the would-be approvers, with nothing executed and nothing
  resumable: a pre-ticket answer to "what would this break, and who would it concern?".
- **The evidence webhook** (`EVIDENCE_WEBHOOK_URL`) POSTs each approval event with the trial's
  evidence packet — findings with citations, risk factors, the plan or safer alternative, the
  run-page link — so your existing ticket carries the analysis its approver was missing. A
  reference receiver that posts the packet onto an existing GitHub issue ships in
  [`backend/scripts/evidence_receiver.py`](../backend/scripts/evidence_receiver.py).
