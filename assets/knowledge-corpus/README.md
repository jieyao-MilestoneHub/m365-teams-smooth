# Knowledge corpus

The source documents for the Change Court knowledge base (Foundry IQ over Azure AI Search). These are
written as a **realistic company knowledge base** — everyday policies, meeting notes, and reference
docs — not as demo-tailored snippets. `backend/scripts/seed_knowledge.py` chunks each file by `##`
section, generates an Anthropic-style **contextual prefix** per chunk, embeds `context + chunk`, and
pushes to the index; retrieval is hybrid (BM25 + vector) + semantic rerank.

The corpus is deliberately **noisy** so retrieval can be tested against distractors, not assumed.
Three roles:

## Targets (a trial should retrieve these)
- `policies/release-change-management.md` — Reschedule trial (controlling policy for a date change).
- `policies/meeting-follow-through.md` + `meetings/2026-06-08-projectx-standup.md` — Meeting Actions.
- `policies/status-reporting.md` — Weekly Report.
- `policies/customer-commitment-ga-readiness.md` — Customer Promise (secondary).
- `policies/third-party-vendor-access.md` — Vendor Access (secondary).
- `reference/projectx-launch-plan.md` — Reschedule context (milestone/announcement).

## Adversarial near-misses (same vocabulary, wrong doc — the rerank stress test)
- `policies/event-scheduling-guidelines.md` — booking rooms/meetings, not launch-date governance.
- `policies/release-change-management-v1-deprecated.md` — superseded v1; must not outrank the current.
- `meetings/2026-05-25-projecty-standup.md` — a *different* project's standup.
- `reference/status-dashboard-faq.md` — a dashboard tool FAQ, not the reporting policy.

## Off-topic noise (realistic, unrelated)
- `policies/travel-and-expense.md`, `policies/remote-work.md`, `policies/information-security-incident.md`
- `reference/onboarding-checklist.md`, `reference/brand-style-guide.md`, `meetings/2026-06-01-allhands.md`

`backend/scripts/eval_retrieval.py` asserts each trial query ranks its target above the matching
near-miss — the concrete retrieval-quality proof.
