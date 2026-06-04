# Documentation rule — no competition references in shipped docs

**Hard rule.** All shipped, user-facing, or repository-public text describes the product's
**function and architecture only**. It must never mention the hackathon, the Microsoft Agents
League, the competition, judging, scoring, bonus points, prizes, deadlines, or submission.

### Applies to

- `README.md`, `roadmap.md`, `verify.md`
- everything under `docs/`
- code comments and docstrings (Python and TypeScript)
- commit messages and PR descriptions
- the M365 manifests and Adaptive Card copy

### Does NOT apply to

- files under `.claude/rules/` — internal engineering guidance, where
  [hackathon.md](./hackathon.md) intentionally captures the competition context.

### How to phrase things

- ✅ "Produces a reviewable cross-system execution plan and records an audit trail."
- ❌ "Earns the MCP and Adaptive Cards bonus points."
- ✅ "Multi-agent execution is a planned extension."
- ❌ "Connected agents are worth 15 points."

### Quick self-check before committing docs

```
grep -rinE "hackathon|agents league|competition|bonus|judg|rubric|submission|prize|deadline" \
  README.md roadmap.md verify.md docs/ 2>/dev/null
```

This should return nothing.
