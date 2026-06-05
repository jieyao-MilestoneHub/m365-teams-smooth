# ADR-0010: Bot surface for native approval buttons

- **Status:** Accepted
- **Date:** 2026-06-05

## Context

In Copilot Chat the agent's MCP tool results render as narrated text, and plugin-rendered cards
cannot host actions that trigger further tool calls — so the requester and approver had to drive
the approval flow with free-text commands. The Change Court card already carries phase-aware
actions (Send for approval / Give up, Approve / Reject with a note), but no surface could execute
them natively. Teams can, when the card is delivered by a bot. Four decisions were needed: where
the production bot endpoint lives, which card action model to use, how the bot's identity relates
to the existing Entra app, and how a synchronous service emits asynchronous proactive messages.

## Decision

1. **The bot endpoint lives in the backend process.** `POST /api/messages` is a FastAPI route in
   the same process that serves MCP, composed at the `asgi.py` edge. Both surfaces close over the
   one in-process `CourtService` and one database, so a trial opened over MCP is approvable from
   the bot's buttons (and SQLite needs no cross-container sharing). The handler (`app/bot/`) is a
   thin façade over `services/` — the same role `mcp/` and `api/` play; `m365/playground-bot`
   keeps only the credential-free aiohttp host and re-exports the backend's `CourtBot`.
2. **Card actions are `Action.Execute` (universal actions).** The bot answers the
   `adaptiveCard/action` invoke with the re-rendered card, which **replaces the card in place** —
   buttons disappear once a gate is passed, so a second click cannot double-act. Each action's
   `data` retains the `tool` key, so legacy `Action.Submit` value routing (the Playground path)
   resolves through the same `respond()` mapping.
3. **The bot has its own multi-tenant app registration.** The court app stays the single-tenant
   MCP resource server (audience `api://<id>`); the bot app authenticates the Bot Framework
   channel, must be multi-tenant when the Azure subscription's tenant differs from the sign-in
   tenant, and carries its own secret lifecycle. Empty `BOT_APP_ID` keeps the endpoint anonymous
   for local Playground use.
4. **Proactive delivery crosses the sync/async seam through a queue.** Service gates are
   synchronous; `continue_conversation` is async. The `BotCardNotifier` (an `ApprovalNotifier`
   adapter) only enqueues a job; an async `ProactiveSender` owned by the app lifespan drains the
   queue and delivers the card. Conversation references are recorded behind a new
   `ConversationStore` port whenever a user installs or talks to the bot. A `CompositeNotifier`
   fans events to both the activity-feed toast (now chained per trial via `chainId`) and the
   bot-chat card; each channel fails independently and delivery stays best-effort. Because the
   card channel reads trials through the service it notifies for, the composition root builds the
   service first and attaches the composite afterwards (`attach_notifier`).

## Consequences

- The approval flow is button-first end to end: the toast deep-links to the bot chat where the
  actionable card already sits; approvers never have to type.
- One more port (`ConversationStore`) and one read-model table (`conversation_references`);
  recipients without a stored reference silently fall back to toast-only.
- The backend gains a Bot Framework SDK dependency, confined to `app/bot/` and the notifier
  adapter; `services/`, `agent/`, and `domain/` stay SDK-free (DIP intact).
- The in-place refresh makes idempotency visible (acted-on cards lose their buttons), but a card
  pushed proactively to several approvers refreshes only for the one who acts; others see the
  stale card until they act and get the current phase back.
- Azure Bot Service registration (bot resource + Teams channel + multi-tenant app) is one more
  deploy-time step, automated behind `create_bot` in Terraform with documented cross-tenant
  fallbacks.
