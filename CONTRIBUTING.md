# Contributing

Thanks for your interest in contributing! This guide covers how we work so that changes stay easy
to review and the trunk stays healthy.

## Principles

- **One responsibility per pull request.** A PR should do one thing — one adapter, one node, one
  endpoint. If it touches several concerns, split it.
- **Reviewable in ~30 minutes.** Aim for ≤ ~300 lines of substantive change (generated files and
  fixtures excluded). Keep refactors separate from behavior changes.
- `main` is the trunk and is always green (builds, lints, tests pass).

## Workflow

1. Fork or branch from `main`. Use a short-lived branch:
   - `feat/<scope>` — new functionality
   - `fix/<scope>` — bug fix
   - `docs/<scope>` — documentation only
   - `chore/<scope>` — tooling, deps, config
   - `refactor/<scope>` — behavior-preserving change
2. Make your change with tests. Keep commits focused.
3. Open a PR against `main` and fill in the template (what / why / how to test / scope).
4. A PR merges when CI is green and it has at least one approving review. We **squash-merge** and
   delete the branch afterward.

Never push directly to `main`; never force-push shared branches.

## Working in parallel

Work is tracked as GitHub issues across five phase milestones, labeled by `area:*` and by readiness
(`ready` = no unmet dependencies, `blocked` = waiting on a dependency listed in the issue).

- **Claim an issue** by assigning it to yourself before starting, so other sessions don't duplicate it.
- Take issues from the **`ready`** label; each issue's *Dependencies* section links what must land first.
- **One issue → one branch → one PR** that `Closes #<issue>`. Keep PRs small and single-responsibility.
- Rebase on `main` before opening the PR.

## Commits

Use [Conventional Commits](https://www.conventionalcommits.org/): `feat:`, `fix:`, `docs:`,
`chore:`, `refactor:`, `test:`. Imperative mood, present tense ("add", not "added").

## Local development

```bash
# Backend (FastAPI)
cd backend
uv sync                      # or: poetry install
cp ../.env.example ../.env
uvicorn app.main:app --reload

# Frontend (Next.js)
cd ../frontend
pnpm install
pnpm dev
```

Run the end-to-end verification checklist before opening a PR that affects behavior:

```bash
scripts/verify.sh
```

## Quality gates

- Backend: `ruff check` and `mypy` clean; `pytest` green.
- Frontend: `pnpm lint` and `pnpm build` succeed.
- Documentation describes function and architecture only.
