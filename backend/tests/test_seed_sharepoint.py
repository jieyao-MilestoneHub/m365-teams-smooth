"""The SharePoint seeder's pure helpers + the asset's load-bearing structure."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.seed_sharepoint import folder_payload


def test_folder_payload_creates_a_folder_idempotently() -> None:
    p = folder_payload("CustomerData")
    assert p["name"] == "CustomerData"
    assert p["folder"] == {}
    # "fail" so a re-run no-ops on an existing folder rather than duplicating it.
    assert p["@microsoft.graph.conflictBehavior"] == "fail"


def test_library_asset_has_the_customer_data_marker() -> None:
    spec = json.loads(
        (Path(__file__).resolve().parents[2] / "assets" / "sharepoint" / "library.json")
        .read_text(encoding="utf-8")
    )
    assert spec["library"] == "ProjectX"  # the path the Vendor Access trial reads
    names = {f["name"] for f in spec["folders"]}
    # The real adapter flags customer data when a child folder is named "customerdata".
    assert any(n.lower() == "customerdata" for n in names)
    assert "LaunchAssets" in names  # the safe, shareable counterpart


def test_calendar_asset_freeze_window_covers_the_demo_target_date() -> None:
    calendar = json.loads(
        (
            Path(__file__).resolve().parents[2]
            / "assets"
            / "sharepoint"
            / "change-freeze-calendar.json"
        ).read_text(encoding="utf-8")
    )
    freezes = calendar["freezes"]
    # The breach evidence checks start <= target <= end; the seeded window must cover the
    # scenario's requested date (2026-06-22) and mirror the mock's window.
    assert any(f["start"] <= "2026-06-22" <= f["end"] for f in freezes)
