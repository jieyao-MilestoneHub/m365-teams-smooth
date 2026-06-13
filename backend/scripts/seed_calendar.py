"""Seed the demo mailbox's Outlook calendar so the ``outlook:real`` evidence path reads real events.

Pushes the realistic calendar in ``assets/outlook-calendar/calendar.json`` into the configured
mailbox (``OUTLOOK_CALENDAR_UPN``) via app-only Microsoft Graph. Idempotent: every seeded event
carries a marker in its body, so a re-run deletes its own prior events and recreates them without
touching the mailbox's real entries.

Requirements: the ``GRAPH_*`` app credentials and the Graph app's **Calendars.ReadWrite**
*application* permission with admin consent in the sign-in tenant. (The trials only *read*; this
write path exists solely to populate the demo calendar.)

Reusable by ``scripts.setup_demo`` via :func:`audit` (read-only presence check) and :func:`apply`
(idempotent reseed).

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
# The marker the live Outlook adapter stamps on events it CREATES during a trial's execution
# (mirrors app/adapters/integrations/real_outlook.py:_CREATED_MARKER). A reset clears these too,
# so an accepted plan's residue event never shifts the next take's safe-alternative date.
_CREATED_MARKER = "[change-court]"
_LOGIN = "https://login.microsoftonline.com"
_GRAPH = "https://graph.microsoft.com/v1.0"
_CALENDAR = Path(
    os.environ.get(
        "OUTLOOK_CALENDAR_JSON",
        Path(__file__).resolve().parents[2] / "assets" / "outlook-calendar" / "calendar.json",
    )
)


def _credentials_ready() -> bool:
    """True when the app-only Graph credentials and the target mailbox are configured."""
    required = ("GRAPH_TENANT_ID", "GRAPH_CLIENT_ID", "GRAPH_CLIENT_SECRET", "OUTLOOK_CALENDAR_UPN")
    return all(os.environ.get(k) for k in required)


def _spec() -> dict[str, Any]:
    spec: dict[str, Any] = json.loads(_CALENDAR.read_text(encoding="utf-8"))
    return spec


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


def _events_with(g: httpx.Client, upn: str, *markers: str) -> list[dict[str, Any]]:
    """The mailbox's events whose body carries any of the given markers."""
    resp = g.get(f"{_GRAPH}/users/{upn}/events?$select=id,subject,body&$top=200")
    resp.raise_for_status()
    return [
        e
        for e in resp.json().get("value", [])
        if isinstance(e.get("body"), dict)
        and any(m in str(e["body"].get("content", "")) for m in markers)
    ]


def _seeded_events(g: httpx.Client, upn: str) -> list[dict[str, Any]]:
    """The mailbox's seeded events (the ones this seeder owns) — for the presence check."""
    return _events_with(g, upn, _MARKER)


def _owned_events(g: httpx.Client, upn: str) -> list[dict[str, Any]]:
    """Every demo-owned event: seeded events plus residue the court created during a take."""
    return _events_with(g, upn, _MARKER, _CREATED_MARKER)


def audit() -> dict[str, object]:
    """Read-only: is the demo calendar already seeded? Never writes.

    Returns ``{ready, present, detail}`` — ``ready`` False when credentials are absent (nothing can
    be checked), ``present`` True when every expected seeded event is on the mailbox.
    """
    expected = len(_spec()["events"])
    if not _credentials_ready():
        return {"ready": False, "present": False, "detail": "GRAPH_*/OUTLOOK_CALENDAR_UPN unset"}
    upn = os.environ["OUTLOOK_CALENDAR_UPN"]
    with httpx.Client(timeout=30, headers={"Authorization": f"Bearer {_token()}"}) as g:
        found = len(_seeded_events(g, upn))
    present = found >= expected
    return {
        "ready": True,
        "present": present,
        "detail": f"{found}/{expected} seeded event(s) on {upn}",
    }


def apply() -> None:
    """Idempotent reseed: delete this seeder's prior events, then recreate from the asset."""
    spec = _spec()
    tz = spec.get("timezone", "UTC")
    payloads = [build_event(ev, tz) for ev in spec["events"]]
    upn = os.environ["OUTLOOK_CALENDAR_UPN"]
    with httpx.Client(timeout=30, headers={"Authorization": f"Bearer {_token()}"}) as g:
        base = f"{_GRAPH}/users/{upn}/events"
        stale = [e["id"] for e in _owned_events(g, upn)]
        for eid in stale:
            g.delete(f"{base}/{eid}").raise_for_status()
        print(f"removed {len(stale)} previously-seeded or court-created event(s)")
        for p in payloads:
            g.post(base, json=p).raise_for_status()
        print(f"created {len(payloads)} event(s) — calendar reseeded")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the demo Outlook calendar.")
    parser.add_argument("--dry-run", action="store_true", help="print payloads, no writes")
    args = parser.parse_args()

    spec = _spec()
    tz = spec.get("timezone", "UTC")
    payloads = [build_event(ev, tz) for ev in spec["events"]]
    upn = os.environ.get("OUTLOOK_CALENDAR_UPN", "<OUTLOOK_CALENDAR_UPN unset>")
    print(f"calendar: {len(payloads)} event(s) for {upn}")

    if args.dry_run:
        for p in payloads:
            print(f"  {p['start']['dateTime'][:16]}  {p['subject']}")
        return

    apply()


if __name__ == "__main__":
    main()
