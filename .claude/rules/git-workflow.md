# Git workflow — open source, small reviewable PRs

This is a public open-source repository. The overriding constraint: **any reviewer can review a PR
in ≤ 30 minutes, and every PR carries a single responsibility.** Optimize for reviewability over
batching.

## Branching

- Trunk is **`main`**. It is always green (builds, lints, tests pass).
- Work on short-lived branches off `main`:
  - `feat/<scope>` — new functionality
  - `fix/<scope>` — bug fix
  - `docs/<scope>` — documentation only
  - `chore/<scope>` — tooling, deps, config
  - `refactor/<scope>` — behavior-preserving change
- **Never push directly to the default branch.** Never force-push shared branches.

## Pull requests

- **One responsibility per PR.** A PR that touches the graph AND adds an adapter AND edits docs is
  too big — split it.
- Target ≤ ~300 changed lines of substantive code (generated files/fixtures excluded). If larger,
  justify in the description or split.
- Keep refactors separate from behavior changes — never mix.
- A PR is mergeable only when CI is green and it has at least one approving review.
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

The [roadmap](../../roadmap.md) milestones are already decomposed into single-responsibility PRs.
When implementing, follow that slicing — one adapter per PR, one node per PR, one router per PR.
