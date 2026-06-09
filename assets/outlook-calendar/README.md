# Outlook calendar (demo mailbox)

`calendar.json` is the realistic calendar seeded into the demo mailbox
(`OUTLOOK_CALENDAR_UPN`) so the `outlook:real` evidence path reads genuine Microsoft Graph events
instead of mock data. It is an ordinary eng-lead's week around the Project X launch — standups, 1:1s,
focus time, a dentist appointment — with two **load-bearing** entries the trials depend on:

- **`Board review` — 2026-06-16** → the reschedule-conflict driver. `move the rehearsal to 2026-06-16`
  collides with it → refused + safe alternative.
- **`SSO Security Review` — 2026-06-18** → the Customer Promise blocker: a security review *after* the
  promised 2026-06-17 GA date.

The rest is realistic noise so the mailbox reads like a real person's calendar, not two demo events.

## Seeding
`backend/scripts/seed_calendar.py` pushes these into the configured calendar via app-only Microsoft
Graph (idempotent — it removes its own previously-seeded events by subject + day, then recreates).

```bash
cd backend && uv run python -m scripts.seed_calendar          # --dry-run to preview
```

Requirements: the `GRAPH_*` app credentials (already configured) and the Graph app must hold the
**`Calendars.ReadWrite`** *application* permission with admin consent in the sign-in tenant
(`Calendars.Read` alone suffices for the read-only evidence path once events exist). See the
[Microsoft Graph references](../../docs/README.md#microsoft-365--azure-service-reference).
