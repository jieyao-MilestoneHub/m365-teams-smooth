# Real SharePoint (Microsoft Graph) — folder evidence

The Vendor Access trial reads a project folder and refuses over-broad access when it holds customer
data. Two providers satisfy the same adapter surface:

- **Mock** (default): `MockSharePointAdapter` returns seeded folders, zero credentials.
- **Real**: `RealSharePointAdapter` lists a configured site's document library over **app-only
  Microsoft Graph**. The grant (write) stays dry-run only — the read evidence path is what goes real.

## What "real" needs
1. **`GRAPH_*` app credentials** (shared with Outlook — see [outlook.md](outlook.md)).
2. **`Sites.Read.All`** *application* permission with admin consent (and **`Sites.ReadWrite.All`** only
   to seed the library via the script rather than the SharePoint UI).
3. **`SHAREPOINT_SITE_ID`** — the site's composite id (`hostname,siteCollectionId,webId`).
4. **`integration_mode` includes `sharepoint:real`**.

## What the trial reads — and the library it needs
The trial reads the path `/ProjectX`. The adapter treats the **first segment as a document library
(drive) name**, lists its root, and flags **customer data** when a child folder is named `CustomerData`
(marker `customerdata`). So the site needs a document library named **`ProjectX`** whose root holds:

- **`CustomerData`** — the load-bearing folder; its presence drives the refusal → least-privilege +
  expiry + auto-revoke.
- **`LaunchAssets`** — the safe, shareable counterpart.

## Seed the library
The layout is version-controlled at [`assets/sharepoint/`](../../assets/sharepoint/). Seed it:

```bash
cd backend
uv run python -m scripts.seed_sharepoint          # --dry-run to preview; idempotent
```

The seeder creates the `ProjectX` library (if missing), the two folders, and placeholder files. It
needs `Sites.ReadWrite.All`. Alternatively, create the `ProjectX` document library and the two folders
in the SharePoint UI (one-time, ~1 min) — then only `Sites.Read.All` is required at runtime.

## Turn it on & verify
```bash
az containerapp update -n changecourt -g changecourt-rg \
  --set-env-vars INTEGRATION_MODE="github:real,outlook:real,sharepoint:real"
```
Submit an over-broad ProjectX access request: the `[sharepoint]` evidence comes from the real library,
the decisive row cites the real **CustomerData** folder, and the court refuses → safe alternative. If
customer data isn't detected, the `CustomerData` folder is missing (re-seed); a `403` means the app
lacks `Sites.Read.All` consent.
