> ⚠ **Scratch onboarding note.** Read this, then your **first action**:
> `git rm E4_START_HERE.md` and commit — so it never reaches `main`.

# You are in the E4 worktree — "Trust & truth"

Worktree `m365-teams-smooth-e4`, branch **`feat/e4-ci-status`** (already checked out, off `main`).
This is one of three parallel enhancement phases from [`roadmap_enhance.md`](./roadmap_enhance.md)
(read its **E4** section + the north star). E1, E2, E3 are done/in-flight elsewhere; the engine is
complete (124+ tests, `scripts/verify.sh` = 13 passed / 0 failed / 3 pending).

## Goal

Make the green suite visible and the docs honest:

1. **GitHub Actions CI** — new `.github/workflows/ci.yml` running, on push + PR:
   `actions/checkout@v6` → `astral-sh/setup-uv@v3` → `cd backend && uv sync` →
   `uv run ruff check` → `uv run mypy` → `uv run pytest`. (Optionally also `scripts/verify.sh`.)
   Today only `.github/workflows/security.yml` (gitleaks) exists — add CI alongside it.
2. **README badge** — add the CI status badge near the top of `README.md`:
   `![CI](https://github.com/jieyao-MilestoneHub/m365-teams-smooth/actions/workflows/ci.yml/badge.svg)`
3. **Fix `roadmap.md` status** — the phase badges are stale (`☐ todo` for everything) and contradict
   the implemented state. Flip them to the truth: Phase 1–4 done locally → `☑`; Phase 5 (Teams
   surface) → `◐` with the tenant as the only remaining blocker. Keep it product-focused.

## You own (and only you may edit)

`.github/workflows/ci.yml` (new) · `roadmap.md` · `README.md` (the badge line). **Do not** touch
backend code, planners, cards, or the bot dir (other phases own those).

## Conventions (this repo)

- `uv` is the toolchain; put it on PATH and `unset VIRTUAL_ENV` first. Gates must be clean:
  `cd backend && uv run ruff check && uv run mypy && uv run pytest`; `scripts/verify.sh` stays
  **13/0/3**; shipped docs (README, roadmap.md, verify.md, docs/, m365/) must contain **no**
  competition words (the verify.sh grep enforces it).
- One small PR (≤ ~300 lines), `Closes`/clear body, **squash-merge with `--admin --delete-branch`**,
  keep `main` green. Commit trailer:
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- Leave the pre-existing untracked `CLAUDE.md` / `.claude/rules/hackathon.md` / `ent_agent.md` alone.

## Definition of done

Green CI badge on the README; `roadmap.md` reflects reality; `scripts/verify.sh` 13/0/3; PR merged.
