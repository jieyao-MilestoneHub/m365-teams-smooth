# Adaptive Cards

The **Change Court card** is built at runtime from a trial's data by `backend/app/mcp/cards.py`
(`build_change_court_card` / `build_verdict_result_card`), following the bindings in
[`docs/reference/mcp-and-card-contract.md`](../../docs/reference/mcp-and-card-contract.md).

- [`change-court.sample.json`](./change-court.sample.json) — an illustrative card rendered for the
  Customer Promise trial (the unsafe-promise → safe-alternative case), with the live `thread_id`
  replaced by a `{thread_id}` placeholder. It is a reference artifact, not the source of truth.

Verdict buttons are `Action.Submit` actions that post `{thread_id, verdict_type, selected_plan}` back
to the `cast_verdict` MCP tool.
