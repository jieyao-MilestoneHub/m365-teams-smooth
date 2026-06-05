# MCP tools & Adaptive Card contract

The contract the MCP server (tools + resources) and the Change Court Adaptive Card build against.
All of it is a thin façade over the single business layer (`CourtService`); the shapes below mirror
the service DTOs and domain types in [domain & capability schema](./domain-and-capability-schema.md).

## MCP tools

| Tool | Arguments | Returns |
| --- | --- | --- |
| `submit_change` | `raw_request: str`, `source?: str`, `run_mode?: "dry_run" \| "live"` | `TrialSummary` |
| `get_status` | `thread_id: str` | `{ status }` |
| `get_trial` | `thread_id: str` | `TrialRecord` |
| `cast_verdict` | `thread_id: str`, `verdict_type: VerdictType`, `selected_plan?: PlanKind`, `idempotency_key?: str`, `actor?: str` | `CastResult` |

`TrialSummary` (also the card's primary payload):
`{ thread_id, change_id, status, risk_level, requires_approval, unsafe, plan_kind,
verdict_options: string[], errors: string[] }`.

`CastResult`: `{ thread_id, status, audit_id, idempotent }`. `cast_verdict` is **idempotent** — the
same `(thread_id, idempotency_key)` returns the recorded result with `idempotent: true` and never
re-executes. This parity holds across MCP and the (health-only) REST surface.

## MCP resources

| Resource URI | Returns |
| --- | --- |
| `court://trial/{thread_id}` | the full `TrialRecord` (change, impact, options, risk, quorum, verdict, results) |
| `court://audit/{audit_id}` | the append-only `AuditRecord` |
| `court://capabilities` | the merged capability catalog (read + write, per system) |

## Change Court Adaptive Card

The card renders a `TrialRecord` (+ its `TrialSummary`). Field bindings:

- **Header** — the structured change (`change.raw_request`, `change.subject`, `change.due_by`) and a
  risk badge (`risk.level`); an **unsafe** banner when `change.unsafe`.
- **Impact evidence** — one row per `impact.items[]`: `system`, `summary`, `severity`, and any
  `grounded[]` citations (the knowledge layer's sources).
- **Proposed plan** — `options.kind` (feasible / **safe alternative**) and `options.rationale`; one
  row per `options.steps[]` (`capability.name`, `params` summary). When `options.supersedes_request`
  is set, the card states the request was replaced by a safer plan.
- **Approvers** — `quorum.required_approvers[]` (`role`, `reason`).
- **Verdict actions** — one button per `quorum.verdict_options[]`; each `Action.Execute` carries
  the tool name as its `verb` and posts back `{ thread_id, verdict_type, selected_plan }` to
  `cast_verdict` (the payload also keeps `tool`, so `Action.Submit`-style value routing resolves
  identically). The safe-alternative case offers *accept alternative* rather than a plain
  *approve*. When the card is delivered by the bot, the invoke response re-renders the card in
  place — the buttons reflect the trial's new phase.

### Verdict-result card

After a verdict: `status`, `audit_id`, and per `results[]` the `step_id`, `status`
(`ok`/`dry_run`/`failed`/`skipped`), a before→after summary, and any `rollback` hint. In dry-run the
card labels effects **predicted**.

## Notes

- Card templates are data under `m365/adaptive-cards/`; the server builds payloads from the service
  DTOs (no business logic in the card builder).
- All tools and resources are OAuth 2.0-protected on the MCP server; a local dev issuer is used when
  no tenant issuer is configured.
