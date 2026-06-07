# Adaptive Cards

The **Change Court card** is built at runtime from a trial's data by `backend/app/mcp/cards.py`
(`build_change_court_card` / `build_verdict_result_card`), following the bindings in
[`docs/reference/mcp-and-card-contract.md`](../../docs/reference/mcp-and-card-contract.md).

- [`change-court.sample.json`](./change-court.sample.json) — an illustrative card rendered for the
  Customer Promise trial (the unsafe-promise → safe-alternative case), with the live `thread_id`
  replaced by a `{thread_id}` placeholder. It is a reference artifact, not the source of truth.

Verdict buttons are `Action.Execute` (universal) actions whose `verb` names the tool and whose data
posts `{thread_id, verdict_type, selected_plan}` back to `cast_verdict`; on the bot surface the
invoke response refreshes the card in place. The data keeps a `tool` key so legacy
`Action.Submit`-style routing resolves identically.

The card also carries a compact **pipeline stage strip** (one subtle `TextBlock` tracing
intake → … → audit for the trial's current status) and — when the deployment configures
`PUBLIC_BASE_URL` and `RUN_LINK_SECRET` — a **View pipeline run** `Action.OpenUrl` deep link (plus
a subtle markdown fallback link) to the read-only run page, where the full courtroom flow can be
inspected live. The card stays the only decision surface; the run page never mutates anything.
