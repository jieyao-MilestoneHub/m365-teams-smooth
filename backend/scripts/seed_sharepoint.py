"""Seed the demo SharePoint site so the ``sharepoint:real`` evidence path reads a real library.

Creates the document library and folder layout in ``assets/sharepoint/library.json`` on the
configured site (``SHAREPOINT_SITE_ID``) via app-only Microsoft Graph. The Vendor Access trial reads
the ``ProjectX`` library root; the presence of a ``CustomerData`` folder is what drives the
over-broad-scope refusal.

Idempotent: existing folders/files are left in place (Graph ``conflictBehavior: fail`` is treated as
"already there"). Requirements: the ``GRAPH_*`` app credentials and **Sites.ReadWrite.All**
*application* permission with admin consent (the trial's read path needs only **Sites.Read.All**).

Reusable by ``scripts.setup_demo`` via :func:`audit` (read-only presence check) and :func:`apply`
(idempotent create).

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


def _credentials_ready() -> bool:
    """True when the app-only Graph credentials and the target site are configured."""
    return all(
        os.environ.get(k)
        for k in ("GRAPH_TENANT_ID", "GRAPH_CLIENT_ID", "GRAPH_CLIENT_SECRET", "SHAREPOINT_SITE_ID")
    )


def _spec() -> dict[str, Any]:
    spec: dict[str, Any] = json.loads(_LIBRARY.read_text(encoding="utf-8"))
    return spec


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


def _root_folder_names(g: httpx.Client, site: str, drive: str) -> set[str]:
    resp = g.get(f"{_GRAPH}/sites/{site}/drives/{drive}/root/children?$select=name,folder&$top=200")
    resp.raise_for_status()
    return {str(c["name"]) for c in resp.json().get("value", []) if c.get("folder") is not None}


def audit() -> dict[str, object]:
    """Read-only: does the demo library + its folders already exist? Never writes.

    Returns ``{ready, present, detail}`` — ``present`` True when the library exists and holds every
    expected folder (``CustomerData`` is the load-bearing one for the refusal path).
    """
    spec = _spec()
    library = spec["library"]
    wanted = {f["name"] for f in spec["folders"]}
    if not _credentials_ready():
        return {"ready": False, "present": False, "detail": "GRAPH_*/SHAREPOINT_SITE_ID unset"}
    site = os.environ["SHAREPOINT_SITE_ID"]
    with httpx.Client(timeout=30, headers={"Authorization": f"Bearer {_token()}"}) as g:
        drive = _drive_id(g, site, library)
        if drive is None:
            return {"ready": True, "present": False, "detail": f"library '{library}' missing"}
        have = _root_folder_names(g, site, drive)
    missing = wanted - have
    present = not missing
    detail = (
        f"library '{library}' + {len(wanted)} folder(s)"
        if present
        else f"library '{library}' present; missing folder(s): {', '.join(sorted(missing))}"
    )
    return {"ready": True, "present": present, "detail": detail}


def apply() -> None:
    """Idempotent create: the library (if missing), its folders, and placeholder files."""
    spec = _spec()
    library = spec["library"]
    folders = spec["folders"]
    site = os.environ["SHAREPOINT_SITE_ID"]
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the demo SharePoint library.")
    parser.add_argument("--dry-run", action="store_true", help="print the plan, no writes")
    args = parser.parse_args()

    spec = _spec()
    library = spec["library"]
    folders = spec["folders"]
    site = os.environ.get("SHAREPOINT_SITE_ID", "<SHAREPOINT_SITE_ID unset>")
    print(f"site: {site}\nlibrary: {library}")
    for f in folders:
        print(f"  folder /{f['name']}  ({len(f.get('files', []))} file(s))")
    if args.dry_run:
        return

    apply()


if __name__ == "__main__":
    main()
