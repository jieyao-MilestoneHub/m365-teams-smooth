# Deploying the backend and going live in Microsoft 365

The court runs fully locally with mocked integrations and a dev OAuth issuer. To exercise it from
**real** Microsoft 365 Copilot Chat / Teams, the backend must be reachable over public HTTPS and the
MCP server must validate **Entra ID** tokens. This guide covers that path. It assumes the engine is
already green locally (`make check`, `scripts/verify.sh`).

The work splits into two halves that meet at environment variables: **hosting the backend** (below)
and **packaging the declarative agent** (see [`../m365/README.md`](../m365/README.md)).

## 1. Host the backend over HTTPS

The backend ships a container image (`backend/Dockerfile`) serving `app.asgi:app` — REST health plus
the OAuth2-protected MCP server at `/mcp`. Any host that runs a container and terminates TLS works;
**Azure Container Apps** keeps the agent and its identity in one tenant and is the reference target.

```bash
# Build and push the image (replace the registry/name).
docker build -f backend/Dockerfile -t <registry>/change-court:latest .
docker push <registry>/change-court:latest
```

Deploy it with the environment below, and note the assigned HTTPS hostname (e.g.
`https://change-court.<region>.azurecontainerapps.io`).

For a quick demo without a cloud host, a **dev tunnel** in front of the local backend also gives a
public HTTPS URL:

```bash
uv run uvicorn app.asgi:app --port 8000   # in backend/
devtunnel host -p 8000 --allow-anonymous  # prints an https://...devtunnels.ms URL
```

### Required environment

| Variable | Value |
| --- | --- |
| `PUBLIC_BASE_URL` | The deployed origin, no trailing slash (e.g. `https://change-court.example.com`). The MCP resource URL is derived as `{PUBLIC_BASE_URL}/mcp`. |
| `OAUTH_ISSUER` | `https://login.microsoftonline.com/<tenant-id>/v2.0` |
| `OAUTH_JWKS_URL` | `https://login.microsoftonline.com/<tenant-id>/discovery/v2.0/keys` |
| `OAUTH_AUDIENCE` | The API's Application ID URI, e.g. `api://<app-id>` |
| `DB_URL` | A persistent database. SQLite on ephemeral container storage loses checkpoints on restart — use Postgres (`postgresql+psycopg://…`) for anything beyond a single session. |
| `INTEGRATION_MODE` | Per-system real/mock. Keep mocks for a reliable demo; set `github:real` with `GITHUB_TOKEN`/`GITHUB_REPO` to use a live repo. |

Setting `OAUTH_ISSUER` + `OAUTH_JWKS_URL` automatically switches the MCP server from the local dev
issuer to **Entra ID JWKS validation** (`app/mcp/security.py`); no code change is needed.

## 2. Register the Entra ID application

In the same tenant (a dedicated **Microsoft 365 dev tenant** with custom-app upload enabled — see
[`adr/0004-development-environment.md`](adr/0004-development-environment.md)):

1. **App registration** → note the *Application (client) ID* and *Directory (tenant) ID*.
2. **Expose an API** → set the Application ID URI to `api://<app-id>` and add a scope `court.use`
   (the scope the MCP resource server requires). This URI is `OAUTH_AUDIENCE`.
3. **Authentication / token** → the MCP plugin obtains tokens via the Teams OAuth connection; create
   that connection and record its reference id as `OAUTH_CONNECTION_ID` for packaging.
4. If/when real Microsoft Graph adapters are enabled (a later step), add the corresponding **API
   permissions** (e.g. `Calendars.ReadWrite`, `Sites.ReadWrite.All`, `User.Invite.All`) and grant
   admin consent. Mocks need no Graph permissions.

## 3. Package and sideload the agent

With the host URL and the values above, build the app package and upload it — see
[`../m365/README.md`](../m365/README.md) (`make package`). Then walk the three trials in Copilot Chat
and tick off the *Pending tenant* checks in [`../verify.md`](../verify.md).

## Reliability fallback

Real integrations depend on tenant state and quotas. Keep the per-system real/mock toggle
(`INTEGRATION_MODE`, or `FORCE_ALL_MOCK=true`) so a live demo can fall back to the deterministic
mocked path at any time.
