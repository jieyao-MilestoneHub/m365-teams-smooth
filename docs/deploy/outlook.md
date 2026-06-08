# Real Outlook (Microsoft Graph) — calendar evidence

The Reschedule and Customer Promise trials read calendar evidence (a date conflict; a security review
after a promised GA date). Two providers satisfy the same adapter surface:

- **Mock** (default): `MockOutlookAdapter` returns seeded events with zero credentials.
- **Real**: `RealOutlookAdapter` reads a configured mailbox's calendar over **app-only Microsoft
  Graph**. Writes stay dry-run only — the adapter never mutates the calendar; only the *read*
  evidence path goes real.

## What "real" needs

1. **`GRAPH_*` app credentials** (already configured): `GRAPH_TENANT_ID`, `GRAPH_CLIENT_ID`,
   `GRAPH_CLIENT_SECRET` — an app registration in the sign-in tenant.
2. **Graph application permission + admin consent** on that app:
   - `Calendars.Read` — required for the trials' read-only evidence.
   - `Calendars.ReadWrite` — additionally required only to *seed* the demo calendar via
     `scripts/seed_calendar.py` (skip it and seed events in the Outlook UI instead).
3. **A real mailbox** at `OUTLOOK_CALENDAR_UPN` (e.g. `joel@agentleague.onmicrosoft.com`) holding the
   events the trials expect.
4. **`integration_mode` includes `outlook:real`** (e.g. `github:real,outlook:real`).

## Seed a realistic calendar

The calendar content is version-controlled at [`assets/outlook-calendar/`](../../assets/outlook-calendar/)
— a realistic eng-lead's week with two load-bearing entries (`Board review` 2026-06-16, `SSO Security
Review` 2026-06-18) embedded in ordinary noise. Push it:

```bash
cd backend
uv run python -m scripts.seed_calendar          # --dry-run to preview; idempotent (marker-based)
```

Keyless is not used here — the seeder uses the `GRAPH_*` client-credentials app, which must hold
`Calendars.ReadWrite` with admin consent.

## Turn it on

Set the mode and roll a new revision:

```bash
az containerapp update -n changecourt -g changecourt-rg \
  --set-env-vars INTEGRATION_MODE="github:real,outlook:real"
```

(Or set `integration_mode` in `infra/terraform.tfvars` — but the live instance is `az`-managed; see
`infra/README.md` → *Updating vs reconciling*.)

## Verify

Submit `move the rehearsal to 2026-06-16`: the impact evidence's `[outlook]` rows now come from the
real calendar, and the decisive conflict cites the real **Board review** event. If the conflict
disappears, the calendar lacks the `Board review` event on 2026-06-16 (re-seed); a `403` from Graph
means the app is missing `Calendars.Read` consent.
