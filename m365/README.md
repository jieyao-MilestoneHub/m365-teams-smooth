# m365 — Microsoft 365 Copilot package

The declarative agent that surfaces the Change Court in Microsoft 365 Copilot / Teams.

| File | Role |
| --- | --- |
| `manifest.json` | Teams app manifest; references the declarative agent under `copilotAgents`. |
| `declarative-agent.json` | The agent: name, instructions, conversation starters, and the action plugin. |
| `ai-plugin.json` | The plugin manifest pointing at the MCP server (its tools). |
| `adaptive-cards/` | The Change Court card (built at runtime; see the sample there). |

## Placeholders

These are resolved at package time (by `package.py` below, or the Microsoft 365 Agents Toolkit) and
are not committed:

- `${{TEAMS_APP_ID}}` — the app id for the dev tenant.
- `${{MCP_HOST_DOMAIN}}` / `${{MCP_SERVER_URL}}` — the public HTTPS host of the MCP server
  (a dev tunnel locally; see `app/asgi.py`, endpoint `/mcp`).
- `${{OAUTH_CONNECTION_ID}}` — the reference id of the Teams OAuth connection (Entra ID).
- `color.png` (192×192) and `outline.png` (32×32) icons — add to `m365/` before packaging.

## Packaging

`package.py` resolves the placeholders from environment variables and zips the manifests + icons into
`m365/build/appPackage.zip` (the file uploaded to a tenant). It fails loudly if an icon or a
placeholder value is missing — nothing partial is written.

```bash
make package        # or: from the repo root, the command below
TEAMS_APP_ID=<guid> MCP_HOST_DOMAIN=change-court.example.com \
MCP_SERVER_URL=https://change-court.example.com/mcp \
OAUTH_CONNECTION_ID=<connection-ref> \
python m365/package.py
```

See [`../docs/deploy.md`](../docs/deploy.md) for hosting the backend over HTTPS and registering the
Entra ID app that supplies these values.

## Verifying in a tenant

Installing and exercising the agent in Copilot Chat / Teams is the *Pending tenant* section of
[`../verify.md`](../verify.md); it needs a dedicated Microsoft 365 dev tenant with custom-app upload
enabled (see [`../docs/adr/0004-development-environment.md`](../docs/adr/0004-development-environment.md)).
