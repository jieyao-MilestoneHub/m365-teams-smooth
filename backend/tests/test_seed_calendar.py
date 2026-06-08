"""The calendar seeder's pure payload builder (network steps are not unit-tested)."""

from __future__ import annotations

from scripts.seed_calendar import _MARKER, build_event


def test_build_event_maps_to_graph_payload_with_marker() -> None:
    ev = {"subject": "Board review", "start": "2026-06-16T09:00:00", "end": "2026-06-16T10:30:00"}
    payload = build_event(ev, "UTC")
    assert payload["subject"] == "Board review"
    assert payload["start"] == {"dateTime": "2026-06-16T09:00:00", "timeZone": "UTC"}
    assert payload["end"] == {"dateTime": "2026-06-16T10:30:00", "timeZone": "UTC"}
    # The marker is what makes re-seeding idempotent without touching real calendar entries.
    assert payload["body"]["content"] == _MARKER


def test_calendar_asset_has_the_load_bearing_events() -> None:
    import json
    from pathlib import Path

    spec = json.loads(
        (Path(__file__).resolve().parents[2] / "assets" / "outlook-calendar" / "calendar.json")
        .read_text(encoding="utf-8")
    )
    by_day = {e["start"][:10]: e["subject"] for e in spec["events"]}
    # The reschedule-conflict driver and the Customer Promise blocker must be present.
    assert by_day.get("2026-06-16") == "Board review"
    review = next(e for e in spec["events"] if e["start"].startswith("2026-06-18"))
    assert "security" in review["subject"].lower() and "review" in review["subject"].lower()
