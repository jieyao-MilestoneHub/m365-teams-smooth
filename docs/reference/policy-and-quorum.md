# Policy & quorum rules

How the `policy+quorum` node turns impact evidence into a risk level, an approval requirement, the
required approvers, and the verdict options offered — **deterministically, from data**. Rules are
**rule packs** (data files), not Python branches; the node is a pure interpreter over them. This is
the contract for the policy node (#76), the quorum resolver (#86), and the rule packs (#87). It uses
the types and the evidence tags defined in [domain & capability schema](./domain-and-capability-schema.md).

## Inputs and outputs

- **Input:** the `Change` (its requested actions) and `ImpactEvidence.tags`.
- **Output:** a `RiskResult` (level, score, factors, `requires_approval`, matched rule ids), a
  `Quorum` (required approvers, verdict options, policy), and — when a rule marks the change unsafe —
  `change.unsafe = True`, which steers the `options` node to a safe alternative.

## Evidence tags vocabulary

Tags are emitted by `impact` from read capabilities and matched by rule packs.

| Tag | Meaning | Emitted in |
| --- | --- | --- |
| `schedule.milestone_move` | A dated milestone is being moved. | Reschedule Sync |
| `schedule.calendar_conflict` | Calendar events sit near the new date. | Reschedule Sync |
| `schedule.target_date_conflict` | The requested day itself collides with an existing event (unsafe). | Reschedule Sync |
| `schedule.planner_shift` | Planner tasks must shift. | Reschedule Sync |
| `comms.pending_announcement` | An announcement references the old date. | Reschedule Sync |
| `meeting.action_items_found` | The meeting discussion left spoken follow-ups to track. | Meeting Actions |
| `report.activity_collected` | Recent activity was collected for a status report. | Weekly Report |
| `github.blocking_issues_open` | Open issues block the promised capability. | Customer Promise |
| `crm.renewal_at_risk` | The account has material renewal value tied to the promise. | Customer Promise |
| `security.review_after_due_date` | The security review lands after the requested target date. | Customer Promise |
| `access.ambiguous_duration` | The request's duration is unspecified ("until done"). | Vendor Access |
| `access.overbroad_scope` | The requested scope is wider than necessary. | Vendor Access |
| `data.customer_data_present` | The target location holds customer data. | Vendor Access |

## Rule pack format

One pack per trial family, loaded and validated into pydantic models by the rule loader. Example
(Customer Promise):

```yaml
id: customer_promise
match:
  any_action_capability: [crm.add_note, github.comment_issue]   # which changes this pack governs
risk_factors:                       # additive scoring, keyed on evidence tags
  - id: blocking_issues_open
    when_tag: github.blocking_issues_open
    weight: 30
  - id: renewal_at_risk
    when_tag: crm.renewal_at_risk
    weight: 20
  - id: review_after_due_date
    when_tag: security.review_after_due_date
    weight: 50
    marks_unsafe: true              # any unsafe factor forces options -> safe_alternative
risk_bands: { low: 0, medium: 30, high: 60 }
quorum:
  approvers:
    - role: security_lead
      when_tag: security.review_after_due_date
    - role: account_owner
      when_tag: crm.renewal_at_risk
  policy: all
verdict_options:
  default: [approve, request_revision, reject]
  when_unsafe: [accept_alternative, request_revision, reject]
  when_high_risk_internal: [approve, approve_internal_only, request_revision, reject]
```

### Interpretation algorithm (deterministic)

1. **Select pack:** the first pack whose `match.any_action_capability` intersects the change's
   requested-action capabilities.
2. **Score:** sum the `weight` of every `risk_factor` whose `when_tag` is present in
   `ImpactEvidence.tags`. Map the total to a `RiskLevel` via `risk_bands`
   (`score >= high` → HIGH, `>= medium` → MEDIUM, else LOW). `requires_approval = level >= MEDIUM`.
3. **Unsafe:** if any matched factor sets `marks_unsafe: true`, set `change.unsafe = True` and record
   the violated constraint. (The same constraint check is a shared pure function the `options` node
   calls, so it can build the safe alternative without depending on node ordering.)
4. **Quorum:** add an `Approver(role, reason, derived_from_tag)` for each approver rule whose
   `when_tag` fired. `policy` is `all` (every listed approver) unless the pack says `any`.
5. **Verdict options:** choose the list by outcome — `when_unsafe` if unsafe, else
   `when_high_risk_internal` if HIGH, else `default`.

Matched factor ids and the pack id are recorded in `RiskResult.matched_rule_ids` for the audit.

## Expected outcomes per trial

| Trial | Fired tags | Score / level | Unsafe? | Required approvers | Verdict options |
| --- | --- | --- | --- | --- | --- |
| **Reschedule Sync** | `schedule.milestone_move` (40), `schedule.calendar_conflict` (20), `schedule.planner_shift` (10), `comms.pending_announcement` (10) | 80 / **HIGH** | no | `eng_lead`, `comms` | approve · approve_internal_only · request_revision · reject |
| **Reschedule — conflicting date** | the four above + `schedule.target_date_conflict` (30, unsafe) | 110 / **HIGH** | **yes** | `eng_lead`, `comms` | accept_alternative · request_revision · reject |
| **Meeting Actions** | `meeting.action_items_found` (10) | 10 / **LOW** | no | — (requester authority) | approve · request_revision · reject |
| **Weekly Report** | `report.activity_collected` (5) | 5 / **LOW** | no | — (requester authority) | approve · request_revision · reject |
| **Customer Promise** | `github.blocking_issues_open` (30), `crm.renewal_at_risk` (20), `security.review_after_due_date` (50, unsafe) | 100 / **HIGH** | **yes** | `security_lead`, `account_owner` | accept_alternative · request_revision · reject |
| **Vendor Access** | `access.ambiguous_duration` (20), `access.overbroad_scope` (40, unsafe), `data.customer_data_present` (30, conditional) | 90 / **HIGH** | **yes** | `manager` (+ `security_lead` if `data.customer_data_present`) | accept_alternative · request_revision · reject |

Weights live in the rule pack data (`backend/app/agent/policy_rules/packs.py`) and can be tuned
without engine changes. A LOW score sets `requires_approval = False`: the court auto-approves, and
in the identity-aware flow the requester's confirmation at the review gate is what executes.

## Why data, not code

Risk scoring, approver resolution, and verdict options are policy that changes more often than the
engine. Keeping them as validated data files means tuning a trial's behavior is a data edit, the
audit can cite exact rule ids, and the `policy+quorum` node stays a small, well-tested interpreter.
