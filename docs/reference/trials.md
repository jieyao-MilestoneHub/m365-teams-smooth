# The demo trials — inputs, fixtures, and golden expectations

The demo spine: everyday cross-system chores, each put on trial. A trial is a request, the seeded
data it reads, and the court output it must produce. These golden expectations are enforced by
`backend/tests/test_golden_trials.py` and the per-trial tests; the seed data lives in the mock
adapters and the offline knowledge corpus.

Conventions: dates are ISO-8601; all systems run mocked (`FORCE_ALL_MOCK`) so no credentials are
needed. The submitting `run_mode` defaults to `dry_run` (effects predicted, audit marked `DRY_RUN`).

## Trial 1 — Reschedule Sync (feasible, high risk, quorum)

- **Request:** `move the rehearsal to 2026-06-17`
- **Seed:** GitHub milestone "Launch Rehearsal" due `2026-06-10`; Planner tasks due near it; an
  Outlook board review on the 16th; a Teams announcement referencing the original date.
- **Impact tags:** `schedule.milestone_move`, `schedule.calendar_conflict`, `schedule.planner_shift`,
  `comms.pending_announcement`.
- **Risk / safety:** score 80 → **HIGH**, not unsafe.
- **Plan (feasible):** one reschedule ripples four systems — `github.update_milestone_due`
  (→ 2026-06-17), `outlook.create_event` (the moved rehearsal), `planner.shift_task_dates`
  (+7 days), `teams.update_announcement`.
- **Approvers:** `eng_lead`, `comms`.
- **Verdict options:** approve · approve_internal_only · request_revision · reject.
- **Guards:** adding "also delete the old launch repo" → `github.delete_repo` is **rejected**
  (no registered capability), recorded as an error, never planned or executed; an injected Planner
  failure in a live run is **contained** as a FAILED step with a rollback hint (the run does not crash).

### Variant — conflicting date (unsafe → safe alternative)

- **Request:** `move the rehearsal to 2026-06-16`
- **The 16th is occupied** (the seeded board review): the gatherer emits
  `schedule.target_date_conflict` (high severity, grounded), the pack marks the request **unsafe**
  (score 110 → HIGH), and the Defender proposes the **next free day** (2026-06-17) with the same
  four-system ripple — a safe alternative that supersedes the request.
- **Verdict options:** accept_alternative · request_revision · reject (no plain *approve*).

## Trial 2 — Meeting Actions (low risk, requester authority)

- **Request:** `create action items from standup`
- **Seed:** four spoken follow-ups in the Teams standup channel — Alex/API spec by `2026-06-12`,
  Jamie/design sign-off by `2026-06-13`, PM/launch doc by `2026-06-14`, and an undated "let's
  review progress next week".
- **Impact tags:** `meeting.action_items_found`, grounded with a follow-through citation.
- **Risk / safety:** score 10 → **LOW**, not unsafe, **no approver** — the court auto-approves;
  in the identity-aware flow the requester's confirmation at the review gate is what executes.
- **Plan (feasible):** three `planner.create_task` steps (title, owner, due date) +
  `outlook.create_event` for the review that was proposed without a date.
- **Verdict options:** approve · request_revision · reject.

## Trial 3 — Weekly Report (low risk, requester authority)

- **Request:** `post the Project X weekly report`
- **Seed:** four recently closed GitHub issues; two tracked Planner tasks; one calendar meeting.
  With the real GitHub adapter, the closed-issue evidence is the repository's actual recent activity.
- **Impact tags:** `report.activity_collected`, grounded with a reporting-cadence citation.
- **Risk / safety:** score 5 → **LOW**, not unsafe, **no approver**.
- **Plan (feasible):** one `teams.post_message` — the report composed from the gathered counts,
  posted to the project channel.
- **Verdict options:** approve · request_revision · reject.

## Where this is enforced

- Golden table: `backend/tests/test_golden_trials.py` (including the `rehearsal_conflict` variant).
- Per-trial flows: `backend/tests/test_trial_launch_slip.py` (both reschedule paths),
  `test_trial_meeting_actions.py`, `test_trial_weekly_report.py`; guards:
  `backend/tests/test_failure_and_guard.py`.
- Seed data: the mock adapters in `backend/app/adapters/integrations/` and the offline knowledge
  corpus in `backend/app/adapters/knowledge/fake_knowledge.py`.
- The earlier governance trials (customer promise, vendor access) remain wired and tested —
  `test_trial_customer_promise.py`, `test_trial_vendor_access.py` — as additional court
  capabilities beyond the demo spine.
