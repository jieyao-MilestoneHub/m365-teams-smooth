# Real SharePoint (Microsoft Graph) — folder evidence

The Vendor Access trial reads a project folder and refuses over-broad access when it holds customer
data. Two providers satisfy the same adapter surface:

- **Mock** (default): `MockSharePointAdapter` returns seeded folders, zero credentials.
- **Real**: `RealSharePointAdapter` lists a configured site's document library over **app-only
  Microsoft Graph** and performs a contained grant: a LIVE `grant_folder_permission` issues a real
  least-privilege, time-boxed Graph invite. Under DRY_RUN it is predicted, not applied.

## What "real" needs
1. **`GRAPH_*` app credentials** (shared with Outlook — see [outlook.md](outlook.md)).
2. **`Sites.ReadWrite.All`** *application* permission with admin consent — required at runtime for the
   LIVE grant (and for seeding the library). Read-only evidence alone needs only `Sites.Read.All`; a
   missing `Sites.ReadWrite.All` consent surfaces as a contained `403` on the grant.
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
customer data isn't detected, the `CustomerData` folder is missing (re-seed); a `403` on a read means
the app lacks `Sites.Read.All` consent.

When the safe alternative runs LIVE (`DRY_RUN_DEFAULT=false`), approving it grants real read access to
`/ProjectX/LaunchAssets` for the principal via `POST /drives/{driveId}/items/{itemId}/invite`
(`sendInvitation:false`, `requireSignIn:true`, roles `["read"]`, `expirationDateTime` from `expiry`).
`expirationDateTime` is best-effort for app-only invites — the `entra.schedule_access_revoke` step is
the authoritative auto-revoke. A `403` on the grant means the app lacks `Sites.ReadWrite.All` consent.
