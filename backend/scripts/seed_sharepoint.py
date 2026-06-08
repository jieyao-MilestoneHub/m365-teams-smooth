"""Seed the demo SharePoint site so the ``sharepoint:real`` evidence path reads a real library.

Creates the document library and folder layout in ``assets/sharepoint/library.json`` on the
configured site (``SHAREPOINT_SITE_ID``) via app-only Microsoft Graph. The Vendor Access trial reads
the ``ProjectX`` library root; the presence of a ``CustomerData`` folder is what drives the
over-broad-scope refusal.

Idempotent: existing folders/files are left in place (Graph ``conflictBehavior: fail`` is treated as
"already there"). Requirements: the ``GRAPH_*`` app credentials and **Sites.ReadWrite.All**
*application* permission with admin consent (the trial's read path needs only **Sites.Read.All**).

Run:  ``cd backend && uv run python -m scripts.seed_sharepoint``  (``--dry-run`` = plan only)
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

import httpx

_LOGIN = "https://login.microsoftonline.com"
_GRAPH = "https://graph.microsoft.com/v1.0"
_LIBRARY = Path(
    os.environ.get(
        "SHAREPOINT_LIBRARY_JSON",
        Path(__file__).resolve().parents[2] / "assets" / "sharepoint" / "library.json",
    )
)


def folder_payload(name: str) -> dict[str, Any]:
    """Graph drive-item payload that creates a folder, or no-ops if it already exists."""
    return {"name": name, "folder": {}, "@microsoft.graph.conflictBehavior": "fail"}


def _token() -> str:
    resp = httpx.post(
        f"{_LOGIN}/{os.environ['GRAPH_TENANT_ID']}/oauth2/v2.0/token",
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


def _drive_id(g: httpx.Client, site: str, library: str) -> str | None:
    resp = g.get(f"{_GRAPH}/sites/{site}/drives?$select=id,name&$top=100")
    resp.raise_for_status()
    return next(
        (str(d["id"]) for d in resp.json().get("value", []) if d.get("name") == library), None
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the demo SharePoint library.")
    parser.add_argument("--dry-run", action="store_true", help="print the plan, no writes")
    args = parser.parse_args()

    spec = json.loads(_LIBRARY.read_text(encoding="utf-8"))
    library = spec["library"]
    folders = spec["folders"]
    site = os.environ.get("SHAREPOINT_SITE_ID", "<SHAREPOINT_SITE_ID unset>")
    print(f"site: {site}\nlibrary: {library}")
    for f in folders:
        print(f"  folder /{f['name']}  ({len(f.get('files', []))} file(s))")
    if args.dry_run:
        return

    with httpx.Client(timeout=30, headers={"Authorization": f"Bearer {_token()}"}) as g:
        drive = _drive_id(g, site, library)
        if drive is None:
            # Create the document library (a SharePoint list), then wait for its drive to surface.
            g.post(
                f"{_GRAPH}/sites/{site}/lists",
                json={"displayName": library, "list": {"template": "documentLibrary"}},
            ).raise_for_status()
            for _ in range(10):
                time.sleep(3)
                drive = _drive_id(g, site, library)
                if drive:
                    break
            if drive is None:
                raise SystemExit(f"library '{library}' created but its drive has not surfaced yet")
            print(f"created document library '{library}'")

        for folder in folders:
            resp = g.post(f"{_GRAPH}/sites/{site}/drives/{drive}/root/children",
                          json=folder_payload(folder["name"]))
            if resp.status_code not in (201, 409):  # 409 = already exists (conflictBehavior: fail)
                resp.raise_for_status()
            for fname in folder.get("files", []):
                body = f"{fname} — demo placeholder for {library}/{folder['name']}.\n"
                put = g.put(
                    f"{_GRAPH}/sites/{site}/drives/{drive}/root:/{folder['name']}/{fname}:/content",
                    headers={"Content-Type": "text/plain"},
                    content=body,
                )
                if put.status_code not in (200, 201):
                    put.raise_for_status()
            print(f"  ensured /{folder['name']} + {len(folder.get('files', []))} file(s)")
    print("done — SharePoint library seeded")


if __name__ == "__main__":
    main()
