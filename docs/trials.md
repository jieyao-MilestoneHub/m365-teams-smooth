# The three trials — inputs, fixtures, and golden expectations

The demo spine. Each trial is a request, the seeded mock data it reads, and the court output it must
produce. These golden expectations are enforced by `backend/tests/test_golden_trials.py` and the
per-trial tests; the seed data lives in the mock adapters and the offline knowledge corpus.

Conventions: dates are ISO-8601; all systems run mocked (`FORCE_ALL_MOCK`) so no credentials are
needed. The submitting `run_mode` defaults to `dry_run` (effects predicted, audit marked `DRY_RUN`).

## Trial 1 — Launch Slip (feasible, high risk)

- **Request:** `slip the launch from 2026-06-10 to 2026-06-17`
- **Seed:** GitHub milestone "Launch" due `2026-06-10`; Planner tasks due near it; an Outlook event
  on the 17th; a Teams announcement referencing the original date.
- **Impact tags:** `schedule.milestone_move`, `schedule.calendar_conflict`, `schedule.planner_shift`,
  `comms.pending_announcement`.
- **Risk / safety:** score 80 → **HIGH**, not unsafe.
- **Plan (feasible):** `github.update_milestone_due` (→ 2026-06-17), `planner.shift_task_dates`
  (+7 days), `teams.update_announcement`.
- **Approvers:** `eng_lead`, `comms`.
- **Verdict options:** approve · approve_internal_only · request_revision · reject.
- **Guards:** adding "also delete the old launch repo" → `github.delete_repo` is **rejected**
  (no registered capability), recorded as an error, never planned or executed; an injected Planner
  failure in a live run is **contained** as a FAILED step with a rollback hint (the run does not crash).

## Trial 2 — Customer Promise (unsafe → safe alternative)

- **Request:** `promise Customer A that SSO is GA by 2026-06-17`
- **Seed:** GitHub open blocking issues for SSO; CRM "Customer A" renewal value `250000` due
  `2026-09-30`; an Outlook security review for SSO on `2026-06-18` (after the promised date).
- **Impact tags:** `github.blocking_issues_open`, `crm.renewal_at_risk`,
  `security.review_after_due_date` (unsafe), grounded with a GA-readiness citation.
- **Risk / safety:** score 100 → **HIGH**, **unsafe**.
- **Plan (safe alternative, supersedes the request):** `github.comment_issue` (customer due date),
  `outlook.create_event` (security review), `crm.add_note` ("do not promise GA; offer private
  preview"), `outlook.draft_email` (customer reply — a **draft**, never sent),
  `teams.create_escalation_thread`.
- **Approvers:** `security_lead`, `account_owner`.
- **Verdict options:** accept_alternative · request_revision · reject (no plain *approve*).

## Trial 3 — Vendor Access (ambiguous/over-broad → least-privilege)

- **Request:** `give the vendor access to Project X until the campaign is done`
- **Seed:** SharePoint `/ProjectX` holds customer data; `/ProjectX/LaunchAssets` does not.
- **Impact tags:** `access.ambiguous_duration`, `access.overbroad_scope` (unsafe),
  `data.customer_data_present`, grounded with a least-privilege citation.
- **Risk / safety:** score 90 → **HIGH**, **unsafe**.
- **Plan (safe alternative):** `sharepoint.grant_folder_permission` (read-only on
  `/ProjectX/LaunchAssets`, expiry `2026-06-30`), `entra.invite_guest`,
  `entra.schedule_access_revoke` (revoke on `2026-06-30`).
- **Approvers:** `manager`, `security_lead` (the folder holds customer data).
- **Verdict options:** accept_alternative · request_revision · reject.

## Where this is enforced

- Golden table: `backend/tests/test_golden_trials.py`.
- Per-trial flows: `backend/tests/test_trial_*.py`; guards: `backend/tests/test_failure_and_guard.py`.
- Seed data: the mock adapters in `backend/app/adapters/integrations/` and the offline knowledge
  corpus in `backend/app/adapters/knowledge/fake_knowledge.py`.
