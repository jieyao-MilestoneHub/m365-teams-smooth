# One-shot demo setup — audit first, then create what's missing

`scripts.setup_demo` brings the three real-evidence backends to the state the Informed Approval demo
expects, in a single run, once the credentials are in the environment. It is **audit-first**: by
default it only *reviews* whether each resource already exists and prints a status table — it never
writes. It reuses the per-system seeders ([github.md](github.md) · [outlook.md](outlook.md) ·
[sharepoint.md](sharepoint.md)), so this is the orchestrator over the same idempotent logic, not a
second code path.

## What it manages
| Resource | Presence signal (how the audit knows) | Credentials |
| --- | --- | --- |
| **GitHub** milestone `Launch Rehearsal` | the milestone exists in `GITHUB_REPO` | `GITHUB_TOKEN` + `GITHUB_REPO` |
| **Outlook** demo calendar | events carrying the `[seed:change-court-demo]` marker | `GRAPH_*` + `OUTLOOK_CALENDAR_UPN` |
| **SharePoint** `ProjectX` library | the library + its `CustomerData`/`LaunchAssets` folders | `GRAPH_*` + `SHAREPOINT_SITE_ID` |

A resource whose credentials are absent is reported as **skipped**, not failed — configure it and
re-run. This is why the audit is safe to run anywhere: it only inspects what it can reach.

## Use
Load the environment first (the orchestrator reads credentials from the process env):
```bash
cd <repo root>
set -a && . ./backend/.env && set +a        # or export the vars another way

make setup-demo            # audit only — "✓ present" / "✗ missing" / "— skipped" per resource
make setup-demo-apply      # create the missing resources (idempotent; present ones left as-is)
```
Equivalently: `cd backend && uv run python -m scripts.setup_demo [--apply] [--force]`.

- **`--apply`** creates only what the audit reported missing.
- **`--force`** (with `--apply`) reseeds even resources already present — e.g. to reset the milestone
  due date and re-assert the seeded calendar between demo takes.

## Idempotency
Re-running is safe. The calendar seeder deletes its own marked events and recreates them (it never
touches the mailbox's real entries); the SharePoint seeder treats "already exists" as success; the
GitHub seeder resets the existing milestone's due date or creates it if absent. Running `--apply`
when everything is present is a no-op.

## Typical output
```
RESOURCE    CREDS   STATUS      DETAIL
------------------------------------------------------------------------
github      yes     ✓ present   'Launch Rehearsal' in owner/repo (due 2026-06-10T00:00:00Z)
outlook     yes     ✓ present   14/14 seeded event(s) on user@tenant
sharepoint  yes     ✓ present   library 'ProjectX' + 2 folder(s)

All configured resources are present — the demo is ready.
```
