# Change Court — Playground bot

A thin [Bot Framework](https://github.com/microsoft/botbuilder-python) surface that makes the
**Change Court** clickable in the **Microsoft 365 Agents Playground** — with **no Microsoft 365
tenant**. A reviewer types a request, the Change Court Adaptive Card renders, they click a verdict
button (e.g. *Accept alternative*), the run resumes, and a verdict-result card is posted.

## What it is (and is not)

The bot contains **no business logic**. Its single responsibility is to translate Bot Framework
turns into court calls and render the result:

- Card payloads come from the backend's card builders — `app.mcp.cards.build_change_court_card`
  and `build_verdict_result_card`.
- The trial is run by the backend's `CourtService`, **in-process** (the engine is imported from the
  sibling `backend/` project — see `courtbot/__init__.py`). It runs fully mocked
  (`FORCE_ALL_MOCK`), so no credentials are needed.
- The bot only routes turns: text opens a trial; a verdict button's submit data
  (`{thread_id, verdict_type, selected_plan}`) resumes it.

```
Agents Playground ──HTTP──> courtbot (this) ──in-process──> CourtService + cards.py (backend)
```

## Prerequisites

- [`uv`](https://docs.astral.sh/uv/) and Python 3.11+.
- [Node.js](https://nodejs.org/) to run the Agents Playground (the local test tool) via `npx`.

## Run it

1. **Start the bot** (from the repo root):

   ```bash
   make bot
   # or:  cd m365/playground-bot && uv sync && uv run python -m courtbot.server
   ```

   It listens on `http://localhost:3978/api/messages`.

2. **Open the Agents Playground** in a second terminal and point it at the bot endpoint:

   ```bash
   npx @microsoft/teams-app-test-tool@latest start
   ```

   The test tool opens a web chat that connects to `http://localhost:3978/api/messages` by default.
   (You can also launch the Playground from the Microsoft 365 Agents Toolkit if you use it for the
   tenant sideload.)

## Demo walk-through

In the Playground chat:

1. Type: **`promise Customer A that SSO is GA by 2026-06-17`**
   → the Change Court card renders with **⛔ REJECTED as requested**, the decisive evidence, and a
   **safe alternative**, plus verdict buttons.
2. Click **Accept alternative**
   → the run resumes and a result card posts: **✅ Safe alternative executed**, with the per-step
   outcomes and any rollback hints.

Other requests work too, e.g. `give the vendor access to Project X until the campaign is done`
(ambiguous → least-privilege alternative) or `slip the launch from 2026-06-10 to 2026-06-17`
(coordinated multi-system plan).

## Capture the card visual (no tenant)

The Agents Playground renders the **real** Change Court Adaptive Card, so it is the tenant-free way
to get a Teams-style card screenshot or recording:

1. `make bot`, then `npx @microsoft/teams-app-test-tool@latest start` (as above).
2. Type `promise Customer A that SSO is GA by 2026-06-17` and screen-record: the card shows
   **⛔ REJECTED as requested**, the decisive evidence with its citation, and the **safe
   alternative**; clicking **Accept alternative** posts the **✅ Safe alternative executed** result.
3. Repeat for the Vendor Access and Launch Slip requests for the full three-trial reel.

Prefer a static preview? The exact card JSON is checked in under
[`../adaptive-cards/generated/`](../adaptive-cards/generated) (regenerate with `make cards`) — paste
any file into the [Adaptive Cards Designer](https://adaptivecards.io/designer) to render it.

## Configuration

Environment variables (all optional):

| Variable | Default | Purpose |
| --- | --- | --- |
| `BOT_HOST` | `localhost` | Bind host. |
| `BOT_PORT` | `3978` | Bind port (the Playground's default bot endpoint). |
| `BOT_DB_URL` | `sqlite:///./data/playground-bot.db` | File-backed SQLite so a run survives the submit → verdict gap. |

## Develop

```bash
cd m365/playground-bot
uv run ruff check
uv run mypy
uv run pytest
```

The test suite drives the real engine fully mocked (the same path as `backend/scripts/demo.py`):
a request renders the refusal card and a verdict button resumes the run to the result card, plus
fake-backed routing tests.

## Scope

This bot is the tenant-free path — enough to render and click the Change Court card and capture the
visual (see above). Installing the agent in a real Microsoft 365 tenant (Teams sideload, dev tunnel,
live Microsoft Graph writes) is owned by the `m365/` manifests and the environment setup.
