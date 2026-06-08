# Real GitHub — milestone + issue evidence and the live write

GitHub is the one integration that performs a **real write**: the Reschedule trial actually PATCHes a
milestone's due date (when `DRY_RUN_DEFAULT=false`). Two providers satisfy the same adapter surface:

- **Mock** (default): `MockGitHubAdapter` returns seeded milestone/issue data, zero credentials.
- **Real**: `RealGitHubAdapter` reads and writes a configured repository over the GitHub REST API.

## What the adapter reads / writes
- **Reads** (evidence): `github.read_milestone` (the rehearsal milestone's due date), `github.read_blocking_issues`, `github.read_closed_issues` (the weekly report's activity).
- **Writes**: `github.update_milestone_due` (the live milestone move), `github.comment_issue`. Under
  `DRY_RUN` these are predicted; with `dry_run_default=false` the milestone PATCH fires for real.

## Configuration
```
INTEGRATION_MODE=github:real        # (plus outlook:real,sharepoint:real for the full demo)
GITHUB_TOKEN=<PAT or fine-grained token>
GITHUB_REPO=<owner>/<name>          # a throwaway repo you control
```
Token permissions: **Issues — Read and write** (covers milestone PATCH and issue comments). Scope the
token to the single demo repo. No token goes in the image — it rides a Container App secret.

## Seed the demo data
The Reschedule trial reads a milestone titled **`Launch Rehearsal`**. Create it in the demo repo with
a pre-trial due date, and reset it to that date between takes (the trial moves it to 2026-06-17):

```bash
gh api -X PATCH repos/<owner>/<name>/milestones/<n> -f due_on=2026-06-10T00:00:00Z -f state=open
```

The Weekly Report trial reads the repo's recently **closed issues**, so a few closed issues make its
aggregation real.

## Verify
Submit `move the rehearsal to 2026-06-17` and approve: the run page's GitHub lane shows
`due_on: 2026-06-10 → 2026-06-17` as a real change; the milestone in GitHub updates. A `404`/`milestone
not found` means the `Launch Rehearsal` milestone is missing; a `403` means the token lacks Issues
write.
