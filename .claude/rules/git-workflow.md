# Git workflow — open source, small reviewable PRs

This is a public open-source repository. The overriding constraint: **any reviewer can review a PR
in ≤ 30 minutes, and every PR carries a single responsibility.** Optimize for reviewability over
batching.

## Current stage — PR-first (collaborating in parallel)

Multiple machines/sessions now work in parallel, so the default is **one issue → one branch → one
pull request that `Closes #<issue>`**. This keeps changes isolated and avoids cross-session
conflicts. Pick work from the `ready` label and self-assign the issue to claim it.

**Direct pushes to `main` are allowed only as an exception** — trivial or urgent fixes (typos, a
broken build, a one-line hotfix). Everything substantive goes through a PR. `main` is protected:
PRs require one approving review, with admin bypass allowed; while solo, an admin merges a green PR
via bypass. Keep `main` green; never force-push or rewrite published history.

## Branching

- Trunk is **`main`**. It is always green (builds, lints, tests pass).
- Work on short-lived branches off `main`:
  - `feat/<scope>` — new functionality
  - `fix/<scope>` — bug fix
  - `docs/<scope>` — documentation only
  - `chore/<scope>` — tooling, deps, config
  - `refactor/<scope>` — behavior-preserving change
- **Never push directly to `main` for substantive work** — use a branch + PR (see *Current stage*
  above for the narrow exception). Never force-push or rewrite published history on a shared branch.

## Pull requests

- **One responsibility per PR.** A PR that touches the graph AND adds an adapter AND edits docs is
  too big — split it.
- Target ≤ ~300 changed lines of substantive code (generated files/fixtures excluded). If larger,
  justify in the description or split.
- Keep refactors separate from behavior changes — never mix.
- A PR is mergeable when CI is green and it has one approving review (branch protection). While
  solo, an admin may merge a green PR via admin bypass.
- **Squash-merge** into `main`; delete the branch after merge.

## PR description template

```
## What
<one or two sentences>

## Why
<the need this addresses>

## How to test
<exact commands / steps a reviewer runs locally>

## Scope
<what is intentionally NOT in this PR>
```

## Commits

- Conventional commits: `feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:`.
- Imperative mood, present tense ("add", not "added").
- Commit messages and PR bodies describe **function and architecture** — never the competition
  (see [docs.md](./docs.md)).

## Slicing guidance

The milestones (tracked as GitHub issues) are already decomposed into single-responsibility PRs.
When implementing, follow that slicing — one adapter per PR, one node per PR, one router per PR.
