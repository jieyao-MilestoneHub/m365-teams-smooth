# Domain & capability schema

The court's pure domain types (`backend/app/domain/`) and the **capability catalog** every adapter
registers. These types carry state across the pipeline `intake → impact → options → policy+quorum →
[verdict] → execute → audit`; the catalog is what `intake` validates requested actions against (the
hallucination guard) and what every `ExecutionStep` binds to. Domain types import no framework or
SDK. This spec is the contract for the domain models (issue #61), the nodes, and the adapters.

## Conventions

- Field names are `snake_case`; types are pydantic models unless noted.
- IDs are strings (UUID or a stable slug). Timestamps are ISO-8601 UTC.
- A **capability** is named `"<system>.<verb>_<object>"`, e.g. `github.update_milestone_due`.
- Capabilities split into **read** (evidence for `impact`) and **write** (actions for `execute`).

## Enums

| Enum | Values | Meaning |
| --- | --- | --- |
| `RunMode` | `DRY_RUN`, `LIVE` | First-class state field; DRY_RUN predicts effects with no side effects. |
| `RiskLevel` | `LOW`, `MEDIUM`, `HIGH` | Output of policy scoring; banded from a numeric score. |
| `ChangeStatus` | `INTAKE`, `EVALUATING`, `AWAITING_VERDICT`, `EXECUTING`, `DONE`, `BLOCKED`, `FAILED` | Lifecycle of a trial. |
| `CapabilityKind` | `READ`, `WRITE` | Read = evidence gathering; write = an action that mutates a system. |
| `VerdictType` | `approve`, `approve_internal_only`, `request_revision`, `reject`, `accept_alternative` | The options a reviewer may cast. |
| `ApproverRole` | `eng_lead`, `security_lead`, `account_owner`, `manager`, `comms` | Roles a quorum can require. |
| `PlanKind` | `feasible`, `safe_alternative` | Whether the plan fulfils the request or replaces it with a safer one. |
| `StepStatus` | `ok`, `failed`, `skipped`, `dry_run` | Outcome of a single execution step. |

## Core types

### Change & requested actions
| Type | Fields | Notes |
| --- | --- | --- |
| `Change` | `change_id, raw_request, source, subject?, deadline?, requested_actions: list[RequestedAction], status: ChangeStatus, unsafe: bool` | Structured form of the request produced by `intake`. `unsafe` is set when a policy constraint is violated. |
| `RequestedAction` | `system, capability_name, verb, params: dict` | One intended action parsed from the request, bound to a catalog capability by `(system, capability_name)`. |

### Capabilities
| Type | Fields | Notes |
| --- | --- | --- |
| `Capability` | `system, name, kind: CapabilityKind, description, params_schema: dict` | Declared by each adapter via `capabilities()`. `params_schema` is JSON Schema used to validate action params. |
| `CapabilityRef` | `system, name` | Lightweight binding used by `RequestedAction` and `ExecutionStep`. |

### Impact evidence
| Type | Fields | Notes |
| --- | --- | --- |
| `ImpactEvidence` | `items: list[EvidenceItem], tags: list[str]` | Produced by `impact`. `tags` are the machine-readable hooks policy/quorum match on (e.g. `security.review_after_deadline`). |
| `EvidenceItem` | `system, kind, summary, severity, data: dict, grounded: list[GroundedFact]` | One consequence found via a read capability. |
| `GroundedFact` | `claim, source_id, citation` | A fact returned by the `KnowledgePort` (Foundry IQ later), with a citation. |

### Plan
| Type | Fields | Notes |
| --- | --- | --- |
| `ExecutionPlan` | `kind: PlanKind, steps: list[ExecutionStep], rationale, supersedes_request: bool` | `safe_alternative` plans set `supersedes_request=True`. |
| `ExecutionStep` | `step_id, capability: CapabilityRef, params: dict, depends_on: list[str]` | One write action; `params` must validate against the capability's `params_schema`. |
| `StepResult` | `step_id, status: StepStatus, before?, after?, predicted?: PredictedEffect, error?, rollback?: RollbackHint` | Result per step; `before/after` snapshots feed the audit. |
| `PredictedEffect` | `summary, diff: dict` | What a DRY_RUN step *would* do; populated only in DRY_RUN. |

### Risk, quorum, verdict
| Type | Fields | Notes |
| --- | --- | --- |
| `RiskResult` | `level: RiskLevel, score: int, factors: list[RiskFactor], requires_approval: bool, matched_rule_ids: list[str]` | Deterministic output of the policy rule pack. |
| `RiskFactor` | `id, label, weight, evidence_tag` | One scored contribution, tied to an evidence tag. |
| `Quorum` | `required_approvers: list[Approver], verdict_options: list[VerdictOption], policy: "all" \| "any"` | Who must approve and what they may choose. |
| `Approver` | `role: ApproverRole, reason, derived_from_tag` | Derived from impact tags by the rule pack. |
| `VerdictOption` | `type: VerdictType, label` | An offered choice. |
| `Verdict` | `verdict_id, type: VerdictType, selected_plan: PlanKind, actor, note?, idempotency_key` | The cast decision; `selected_plan` picks which plan `execute` runs. |

### Audit (append-only)
| Type | Fields | Notes |
| --- | --- | --- |
| `AuditRecord` | `audit_id, change_id, thread_id, run_mode: RunMode, status: ChangeStatus, trial: TrialRecord, before_after: list[BeforeAfter], rollback_hints: list[RollbackHint], created_at` | Never updated; corrections are new records. |
| `TrialRecord` | `change, impact, options, risk, quorum, verdict, results` | The full reviewable trial. |
| `BeforeAfter` | `system, target, before: dict, after: dict` | One snapshot pair. |
| `RollbackHint` | `step_id, system, instruction, params: dict` | Advisory only — never auto-executed. |

## Capability catalog

The seven systems the three trials need. GitHub runs real (later) or mock; the rest are mock.
Every trial action below maps to exactly one capability — anything not listed is rejected by `intake`.

| System | Capability | Kind | Params (key fields) | Used by |
| --- | --- | --- | --- | --- |
| github | `github.read_milestone` | READ | `repo, milestone` | Launch Slip |
| github | `github.read_blocking_issues` | READ | `repo, label?` | Launch Slip, Customer Promise |
| github | `github.update_milestone_due` | WRITE | `repo, milestone, due_on` | Launch Slip |
| github | `github.create_issue` | WRITE | `repo, title, body` | Launch Slip |
| github | `github.comment_issue` | WRITE | `repo, issue, body` | Customer Promise |
| outlook | `outlook.read_events` | READ | `calendar, window` | Launch Slip |
| outlook | `outlook.read_security_review` | READ | `subject` | Customer Promise |
| outlook | `outlook.create_event` | WRITE | `calendar, title, start, end` | Customer Promise |
| outlook | `outlook.draft_email` | WRITE | `to, subject, body` (draft only — never sent) | Customer Promise |
| planner | `planner.read_tasks` | READ | `plan` | Launch Slip |
| planner | `planner.shift_task_dates` | WRITE | `plan, delta_days` | Launch Slip |
| teams | `teams.read_announcement` | READ | `channel` | Launch Slip |
| teams | `teams.update_announcement` | WRITE | `channel, message` | Launch Slip |
| teams | `teams.create_escalation_thread` | WRITE | `channel, title, body` | Customer Promise |
| crm | `crm.read_account` | READ | `account` (renewal value + date) | Customer Promise |
| crm | `crm.add_note` | WRITE | `account, note` | Customer Promise |
| sharepoint | `sharepoint.read_folder` | READ | `site, path` | Vendor Access |
| sharepoint | `sharepoint.grant_folder_permission` | WRITE | `site, path, principal, role, expiry` | Vendor Access |
| entra | `entra.invite_guest` | WRITE | `email, display_name` | Vendor Access |
| entra | `entra.schedule_access_revoke` | WRITE | `principal, revoke_on` | Vendor Access |

## Hallucination guard (intake contract)

For each `RequestedAction`, `intake`:
1. Looks up `(system, capability_name)` in the registry's merged catalog. No match → raise
   `CapabilityNotFoundError`; the action is **neither planned nor executed**.
2. Validates `params` against the capability's `params_schema`. Invalid → `CapabilityNotFoundError`
   (treated as unsupported).

So "also delete the old launch repo" is rejected: no `github.delete_repo` capability is registered.

## Pipeline data flow

`intake` → `Change` (+ guard) · `impact` → `ImpactEvidence` (items + tags) · `options` →
`ExecutionPlan` (feasible or safe alternative) · `policy+quorum` → `RiskResult` + `Quorum` · verdict
interrupt → `Verdict` · `execute` → `list[StepResult]` · `audit` → `AuditRecord` (append-only).
