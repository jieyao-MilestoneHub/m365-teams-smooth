# m365 — Microsoft 365 Copilot package

The declarative agent that surfaces the Change Court in Microsoft 365 Copilot / Teams.

| File | Role |
| --- | --- |
| `manifest.json` | Teams app manifest; references the declarative agent under `copilotAgents`. |
| `declarative-agent.json` | The agent: name, instructions, conversation starters, and the action plugin. |
| `ai-plugin.json` | The plugin manifest pointing at the MCP server (its tools). |
| `adaptive-cards/` | The Change Court card (built at runtime; see the sample there). |

## Placeholders

These are resolved at package time (e.g. by the Microsoft 365 Agents Toolkit), not committed:

- `${{TEAMS_APP_ID}}` — the app id for the dev tenant.
- `${{MCP_HOST_DOMAIN}}` / `${{MCP_SERVER_URL}}` — the public HTTPS host of the MCP server
  (a dev tunnel locally; see `app/asgi.py`, endpoint `/mcp`).
- `color.png` (192×192) and `outline.png` (32×32) icons — add before packaging.

## Verifying in a tenant

Installing and exercising the agent in Copilot Chat / Teams is the *Pending tenant* section of
[`../verify.md`](../verify.md); it needs a dedicated Microsoft 365 dev tenant with custom-app upload
enabled (see [`../docs/adr/0004-development-environment.md`](../docs/adr/0004-development-environment.md)).
