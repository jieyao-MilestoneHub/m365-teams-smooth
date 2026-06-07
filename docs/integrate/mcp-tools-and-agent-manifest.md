# Exposing a new MCP tool — and reflecting it in the M365 manifests

The MCP server is the court's primary programmatic surface. Tools are deliberately thin: every one
of them delegates to the business layer, so adding a tool is mostly about deciding what the
*service* should do.

## The surface today

**Tools** (`backend/app/mcp/tools.py`):

| Tool | Role |
| --- | --- |
| `submit_change` | Open a trial from a raw request (`run_mode` optional). |
| `get_status` / `get_trial` | Inspect a trial's state / full record. |
| `send_for_approval` / `withdraw_change` | Requester actions (note required / terminal). |
| `list_pending_approvals` / `decide` | Approver queue and decision. |
| `cast_verdict` | Cast a verdict; idempotent across MCP and REST. |
| `acknowledge_outcome` | Requester confirms a concluded trial. |

**Resources:** `court://trial/{thread_id}`, `court://audit/{audit_id}`, `court://capabilities`
(plus `court://metrics` when metrics are enabled).

## Adding a tool — service first

1. **Business logic goes in `services/`.** Implement (or extend) the service method with its
   guards — identity, bounds, idempotency — exactly once. If the behavior should also be reachable
   over REST or the card later, this is what makes that free.
2. **Wrap it thinly** in `backend/app/mcp/tools.py`: validate/parse arguments into typed models,
   call the service, return its DTO. Follow the existing decorator pattern there for correlation
   and error translation — adapter and domain errors must surface as typed tool errors, never as
   stack traces.
3. **No logic in the tool.** If your wrapper grows an `if` that isn't argument shaping, it belongs
   in the service.

The MCP server is OAuth2-protected when deployed; locally a dev issuer applies. Tools receive the
authenticated principal — never accept a caller-supplied identity argument as authority.

## Reflecting it in the M365 package

Three manifests under `m365/` describe the agent to Microsoft 365; update them when the tool
should be visible to the declarative agent:

| File | What to touch |
| --- | --- |
| `m365/ai-plugin.json` | The plugin/tool list the agent may call — add the new tool's name and description. |
| `m365/declarative-agent.json` | Instructions and **conversation starters** — add a starter if users should discover the capability in chat. |
| `m365/manifest.json` | The Teams app manifest — usually unchanged for a new tool. |

The manifests carry `${{PLACEHOLDER}}` tokens (app IDs, the MCP server URL, the OAuth connection);
`m365/package.py` resolves them from the environment and zips the package — `make package`
produces `m365/build/appPackage.zip` for sideloading. See [m365/README.md](../../m365/README.md)
for the placeholder list.

## Card changes

If the tool's output should render on the Change Court card, extend the card templates under
`m365/adaptive-cards/` — they are data, built from service DTOs, and carry no business logic. The
field bindings are documented in
[reference/mcp-and-card-contract.md](../reference/mcp-and-card-contract.md).

## Checklist

- [ ] Service method with guards; unit-tested in isolation.
- [ ] Thin MCP wrapper following the existing decorator pattern.
- [ ] Parity decision made: if the action also exists on REST or the card, behavior (including
      idempotency) must be identical — it's the same service call.
- [ ] `m365/ai-plugin.json` (and starters, if discoverable) updated; package rebuilds cleanly.
- [ ] Contract doc updated: [mcp-and-card-contract.md](../reference/mcp-and-card-contract.md).

## See also

- [ADR-0010 — bot surface for native approval buttons](../reference/adr/0010-bot-surface-for-native-approval-buttons.md)
  — how card actions reach the same services.
- [View ① — Layered architecture](../architecture/01-layered-architecture.html) — why façades stay
  thin.
