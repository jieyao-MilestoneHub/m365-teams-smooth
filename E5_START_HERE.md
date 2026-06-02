> ⚠ **Scratch onboarding note.** Read this, then your **first action**:
> `git rm E5_START_HERE.md` and commit — so it never reaches `main`.

# You are in the E5 worktree — "Tenant-free clickable Teams card"

Worktree `m365-teams-smooth-e5`, branch **`feat/e5-playground-bot`** (already checked out, off `main`).
One of three parallel phases from [`roadmap_enhance.md`](./roadmap_enhance.md) (read its **E5**
section + the north star). This is the reviewer's #1 gap: prove the **"approve in Teams"** moment.

## Goal

In the **Microsoft 365 Agents Playground** (no tenant required): a person types a request →
the **Change Court card** renders → they click a verdict button (e.g. *Accept alternative*) →
the run **resumes** → a verdict-result card is posted. This makes the killer moment demoable
without a tenant.

## Decide first (ask the user)

**Bot stack:** TypeScript (Microsoft 365 Agents Toolkit / Agents Playground default — matches the
`setup/env` worktree) **vs** Python (Microsoft Agents SDK / Bot Framework). Confirm before building.

## Build a THIN surface (SOLID — no business logic in the bot)

Reuse what exists; the bot only renders + forwards:
- **Card payloads** come from `backend/app/mcp/cards.py` —
  `build_change_court_card(thread_id, trial)` and `build_verdict_result_card(trial, status, audit_id)`.
- **Verdict round-trip** uses the existing MCP tools on `app.asgi:app` at `/mcp`
  (`submit_change` → `get_trial` → `cast_verdict`), or call `CourtService` directly if the bot is
  Python. The verdict button already posts `{thread_id, verdict_type, selected_plan}` to `cast_verdict`.
- Run the backend with `cd backend && uv run uvicorn app.asgi:app` (REST + OAuth2 MCP at `/mcp`).

## You own (and only you may edit)

A **new** dir `m365/playground-bot/` (or `bot/`) and a `Makefile` `bot` target. **Do not** edit the
existing `m365/manifest.json` / `ai-plugin.json` / `declarative-agent.json` — the `setup/env` worktree
owns the tenant sideload + dev tunnel. **Do not** edit `README.md` (the E4 worktree owns it) — put
run instructions in your bot dir's own README.

## Conventions (this repo)

- Gates clean for any backend touch: `cd backend && uv run ruff check && uv run mypy && uv run pytest`;
  `scripts/verify.sh` stays **13/0/3**; shipped docs competition-word-free.
- One small PR per slice, **squash-merge `--admin --delete-branch`**, keep `main` green. Trailer:
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- Coordinate with the `setup/env` worktree on anything Teams/tenant. Leave the pre-existing untracked
  `CLAUDE.md` / `.claude/rules/hackathon.md` / `ent_agent.md` alone.

## Definition of done

In the Agents Playground, a typed trial request renders the Change Court card and a verdict button
resumes the run to a result card; the steps are documented in the bot dir's README.
