# assets/

Internally-prepared **domain materials** — the source data we author and curate to make the system
work in a real domain, kept separate from application code (`backend/`), infrastructure (`infra/`),
and the M365 app package (`m365/`).

These are inputs to a build/seed step, not runtime code. They are version-controlled so the domain
setup is reproducible and reviewable.

## Contents
- [`policy-packs/`](policy-packs/) — example rule-pack file for `POLICY_PACKS_PATH` (extend the
  court's governance as data; see `docs/extending.md`).
- [`knowledge-corpus/`](knowledge-corpus/) — the knowledge-base corpus (company policies, meeting
  notes, reference docs) seeded into Foundry IQ by `backend/scripts/seed_knowledge.py`.
