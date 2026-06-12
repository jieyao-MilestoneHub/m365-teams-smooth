# Adaptive Cards

The **Change Court card** is built at runtime from a trial's data by `backend/app/mcp/cards.py`
(`build_change_court_card` / `build_verdict_result_card`).

- [`change-court.sample.json`](./change-court.sample.json) — an illustrative card showing the
  refuse-and-propose-safer shape (rendered here for the Customer Promise capability), with the live
  `thread_id` replaced by a `{thread_id}` placeholder. It is a reference artifact, not the source of
  truth. Run `make cards` to generate the headline **Informed Approval** cards (and `make cards-all`
  for every capability) into `generated/`.

Verdict buttons are `Action.Execute` (universal) actions whose `verb` names the tool and whose data
posts `{thread_id, verdict_type, selected_plan}` back to `cast_verdict`; on the bot surface the
invoke response refreshes the card in place. The data keeps a `tool` key so legacy
`Action.Submit`-style routing resolves identically.

The card also carries a compact **pipeline stage strip** (one subtle `TextBlock` tracing
intake → … → audit for the trial's current status) and — when the deployment configures
`PUBLIC_BASE_URL` and `RUN_LINK_SECRET` — a single subtle **View pipeline run** markdown link to
the read-only run page, where the full pipeline run can be inspected live. The link sits in the
body (one focus per surface, and it renders even in hosts that suppress `Action.OpenUrl`), leaving
the action row dedicated to decisions. The card stays the only decision surface; the run page never
mutates anything.
