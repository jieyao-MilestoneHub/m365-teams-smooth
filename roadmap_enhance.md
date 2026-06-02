# Enhancement roadmap — sharpen the killer capability

This roadmap turns a design review ([`enhance_point.md`](./enhance_point.md)) into a focused,
phased plan. The engine is already complete and green locally; what follows are **enhancements that
make the demo land**, not fixes. We implement them one small PR at a time.

## North star

> **The agent stops an enterprise mistake before it happens, proposes a safer *executable*
> alternative, and only acts after a human approves it — in Teams.**

Every phase below must visibly sharpen that one sentence. The demo leads with the refusal, so the
running order is:

**1) Customer Promise → 2) Vendor Access → 3) Launch Slip.**

(The most striking moment is the agent *refusing* an unsafe customer promise and offering a safe
alternative — not helping a PM move a date.)

## Baseline — already done (the engine)

Complete and verified locally, credential-free: the court pipeline (`intake → impact → options →
policy+quorum → [verdict] → execute → audit`), the **durable verdict interrupt**, **verdict
idempotency**, the **hallucination guard**, the **safe-alternative** generator, all three trials,
the MCP tools/resources over an OAuth2 server (dev issuer + JWKS verifier), the Adaptive Card
builder, the M365 manifests, the real GitHub adapter, and the real Foundry IQ knowledge provider.
**124 tests pass · ruff 0 · mypy 0 · `scripts/verify.sh` = 13 passed / 0 failed / 3 pending (tenant).**

> Note: `roadmap.md`'s phase badges still read `☐ todo` and contradict this state — **E4 corrects
> them**. The single source of truth for status is this baseline and `scripts/verify.sh`.

## Guardrails (apply to every phase)

- **SOLID.** New behaviour enters through ports (`RequestParser`, `LLMProvider`), Open/Closed — the
  court nodes and `services/` stay unchanged. Adapters select real-vs-mock by config.
- **Trials stay reproducible offline.** A deterministic fallback always exists; the LLM only
  enriches. `FORCE_ALL_MOCK` keeps the whole demo credential-free.
- **Small PRs.** One responsibility, ≤ ~300 substantive lines, tests green, `ruff`/`mypy` clean,
  `scripts/verify.sh` stays green. Shipped docs stay product-focused.

---

## E1 — Make the refusal unmissable  ·  *non-tenant*

Goal: the "agent says no, here's the safe path" moment is the first thing anyone sees, and the card
shows *why* at a glance.

- Reorder the demo to Customer Promise → Vendor Access → Launch Slip (`backend/scripts/demo.py`;
  README/HTML demo notes).
- Add a prominent **Decisive Evidence** block to `build_change_court_card`
  (`backend/app/mcp/cards.py`): hoist high-`severity` evidence to the top, e.g.
  *"Security review 2026-06-18 is AFTER the promised 2026-06-17 → UNSAFE"*, with its citation.
- Frame the unsafe outcome as **REJECTED → Safe alternative** (header + the `accept_alternative`
  button reads as adopting the safer plan, not a plain approve). Sharpen the verdict-result card so
  the executed steps read as "the safer plan ran".
- Tests: card assertions for the decisive block and the rejected/safe-alternative framing.

**DoD:** `make demo` opens on the Customer Promise refusal; the card surfaces the decisive
contradiction and the safe alternative without scrolling. *(~2–3 PRs)*

## E2 — Agentic natural-language understanding (real LLM, SOLID)  ·  *code non-tenant; live needs a key*

Goal: it parses what a person actually types ("Can we tell Customer A SSO is ready next Wednesday?",
"Move our launch by a week", "Let the agency into the Project X folder for now"), not three fixed
sentences — while staying reproducible offline.

- New **`RequestParser` port** (`backend/app/ports/request_parser.py`): `parse(raw, *, change_id) -> Change`.
- Refactor `parse_request` (`backend/app/agent/nodes/intake.py`) into
  **`DeterministicRequestParser`** and broaden it (synonyms: move/push/delay/reschedule ·
  tell/commit/promise · let/grant/give + agency/vendor/contractor). This is the always-on fallback.
- Add **`LlmRequestParser`**: an LLM turns free text into a structured `Change` (incl. relative
  dates), which is then **validated against the capability registry** (reuse the existing intake
  guard) and **falls back to the deterministic parser** on low confidence or parse failure.
- Build a real **`LLMProvider`** adapter (Anthropic Claude / Azure OpenAI), selected when
  `LLM_API_KEY` is set; `FakeLLMProvider` stays the default. Extend the LLM port minimally for
  structured output.
- Inject the parser into `IntakeNode` via `backend/app/container.py` (LLM-backed when a key is
  present; deterministic otherwise).
- Tests: **≥3 paraphrases per trial** that land in the same trial (offline-stable on the broadened
  deterministic parser); a stub-LLM test proving LLM → structured → registry-validated; a
  fallback-on-failure test.

**DoD:** each trial accepts ≥3 rephrasings; with a key, open-ended phrasing works; offline trials
remain deterministic and green. *(~4–5 PRs)*

## E3 — Four-system Launch Slip  ·  *non-tenant*

Goal: Launch Slip visibly coordinates **GitHub + Outlook + Planner + Teams**, not three systems.

- Add an Outlook execution step to `plan_launch` (`backend/app/agent/planners.py`) —
  `outlook.create_review_event` (reuse/extend `mock_outlook`'s write capabilities).
- Update the golden + Launch Slip trial tests (plan capability set; the "4 systems" assertion).

**DoD:** the Launch Slip plan touches four systems; tests updated and green. *(~1–2 PRs)*

## E4 — Trust & truth  ·  *non-tenant*

Goal: anyone can see the suite is green, and the docs don't contradict themselves.

- GitHub Actions CI (`.github/workflows/ci.yml`): `uv sync` + `ruff` + `mypy` + `pytest` (optionally
  `scripts/verify.sh`) on push/PR; add a status badge to the README.
- Correct `roadmap.md` phase badges to reflect the real state; mark the tenant items as the only
  remaining blocker.
- *(Optional)* make one evidence source feel real: a checked-in policy markdown that the knowledge
  layer cites, or real GitHub blockers when a token is configured.

**DoD:** a green CI badge on the README; `roadmap.md` status is truthful. *(~2 PRs)*

## E5 — Tenant-free clickable Teams card (the last mile)  ·  *I build; coordinate with the env worktree*

Goal: a reviewer types a request, the **Change Court card renders**, they click **Accept
alternative**, and the run **resumes** — all without a Microsoft 365 tenant.

- A custom-engine agent / bot runnable in the **Microsoft 365 Agents Playground** (no tenant): it
  posts the Change Court card and handles the verdict `Action.Submit` by calling the existing MCP
  tools / `CourtService`, then posts the verdict-result card.
- Reuses `backend/app/mcp/cards.py` for payloads; the bot is a **thin surface** over the MCP tools —
  no business logic in the bot (SOLID). Stack chosen to match the env worktree (Agents Toolkit).
- Full Teams sideload + real Microsoft Graph writes remain the tenant step (env worktree).

**DoD:** in the Agents Playground, a typed request renders the card and a verdict button resumes the
run to a result card. *(~3–4 PRs)*

---

## Sequencing

Implement **E1 → E2 → E3 → E4 → E5**, each as small PRs with their own DoD; `main` stays green
throughout. E1–E4 are fully local; E5 is built locally (Agents Playground) and coordinated with the
environment worktree for the eventual tenant sideload.

## Demo-level definition of done

- `make demo` leads with the Customer Promise refusal and reads as "the agent stopped a mistake".
- Each trial parses ≥3 natural rephrasings into the correct trial.
- Launch Slip coordinates four systems.
- The README shows a green CI badge.
- In the Agents Playground, the Change Court card renders and a verdict button resumes the run.
