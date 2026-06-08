"""Seed the demo mailbox's Outlook calendar so the ``outlook:real`` evidence path reads real events.

Pushes the realistic calendar in ``assets/outlook-calendar/calendar.json`` into the configured
mailbox (``OUTLOOK_CALENDAR_UPN``) via app-only Microsoft Graph. Idempotent: every seeded event
carries a marker in its body, so a re-run deletes its own prior events and recreates them without
touching the mailbox's real entries.

Requirements: the ``GRAPH_*`` app credentials and the Graph app's **Calendars.ReadWrite**
*application* permission with admin consent in the sign-in tenant. (The trials only *read*; this
write path exists solely to populate the demo calendar.)

Run:  ``cd backend && uv run python -m scripts.seed_calendar``  (``--dry-run`` prints payloads only)
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import httpx

_MARKER = "[seed:change-court-demo]"
_LOGIN = "https://login.microsoftonline.com"
_GRAPH = "https://graph.microsoft.com/v1.0"
_CALENDAR = Path(
    os.environ.get(
        "OUTLOOK_CALENDAR_JSON",
        Path(__file__).resolve().parents[2] / "assets" / "outlook-calendar" / "calendar.json",
    )
)


def build_event(ev: dict[str, Any], timezone: str) -> dict[str, Any]:
    """Map a calendar.json entry to a Graph event payload (marked as demo-seeded)."""
    return {
        "subject": ev["subject"],
        "start": {"dateTime": ev["start"], "timeZone": timezone},
        "end": {"dateTime": ev["end"], "timeZone": timezone},
        "body": {"contentType": "text", "content": _MARKER},
    }


def _token() -> str:
    tenant = os.environ["GRAPH_TENANT_ID"]
    resp = httpx.post(
        f"{_LOGIN}/{tenant}/oauth2/v2.0/token",
        data={
            "client_id": os.environ["GRAPH_CLIENT_ID"],
            "client_secret": os.environ["GRAPH_CLIENT_SECRET"],
            "grant_type": "client_credentials",
            "scope": "https://graph.microsoft.com/.default",
        },
        timeout=30,
    )
    resp.raise_for_status()
    return str(resp.json()["access_token"])


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the demo Outlook calendar.")
    parser.add_argument("--dry-run", action="store_true", help="print payloads, no writes")
    args = parser.parse_args()

    spec = json.loads(_CALENDAR.read_text(encoding="utf-8"))
    tz = spec.get("timezone", "UTC")
    payloads = [build_event(ev, tz) for ev in spec["events"]]
    upn = os.environ.get("OUTLOOK_CALENDAR_UPN", "<OUTLOOK_CALENDAR_UPN unset>")
    print(f"calendar: {len(payloads)} event(s) for {upn}")

    if args.dry_run:
        for p in payloads:
            print(f"  {p['start']['dateTime'][:16]}  {p['subject']}")
        return

    with httpx.Client(timeout=30, headers={"Authorization": f"Bearer {_token()}"}) as g:
        base = f"{_GRAPH}/users/{upn}/events"
        resp = g.get(f"{base}?$select=id,subject,body&$top=200")
        resp.raise_for_status()
        items = resp.json().get("value", [])
        stale = [
            e["id"] for e in items
            if isinstance(e.get("body"), dict) and _MARKER in str(e["body"].get("content", ""))
        ]
        for eid in stale:
            g.delete(f"{base}/{eid}").raise_for_status()
        print(f"removed {len(stale)} previously-seeded event(s)")
        for p in payloads:
            g.post(base, json=p).raise_for_status()
        print(f"created {len(payloads)} event(s) — calendar reseeded")


if __name__ == "__main__":
    main()
