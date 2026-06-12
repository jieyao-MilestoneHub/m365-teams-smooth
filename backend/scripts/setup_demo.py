"""One-shot demo-resource setup — audit first, then create only what is missing.

Brings the real-evidence backends to the state the demo expects, in a single run, once the
credentials are in the environment. GitHub and Outlook ground the **Informed Approval** headline;
SharePoint grounds the **Vendor Access** additional capability (skip it if you only run the
headline):

- **GitHub** — the ``Launch Rehearsal`` milestone (the date the request moves) and the demo
  change ticket the evidence receiver posts onto. *Headline.*
- **Outlook** — the demo calendar, incl. the ``Board review`` conflict the request collides with.
  *Headline.*
- **SharePoint** — the ``ProjectX`` document library and its folders. *Vendor Access capability.*

It is **audit-first**: with no flags it only *reviews* whether each resource already exists and
reports a status table — it never writes. Pass ``--apply`` to create the missing pieces (idempotent;
present resources are left as-is unless ``--force`` reseeds them). A resource whose credentials are
absent is reported as *skipped*, not failed — configure it and re-run.

Credentials are read from the environment (load a ``.env`` first, e.g. ``set -a && . ./.env``):
``GRAPH_*`` + ``OUTLOOK_CALENDAR_UPN`` + ``SHAREPOINT_SITE_ID`` (Outlook/SharePoint) and
``GITHUB_TOKEN`` + ``GITHUB_REPO`` (GitHub).

Run:  ``cd backend && uv run python -m scripts.setup_demo``            # audit only
      ``cd backend && uv run python -m scripts.setup_demo --apply``    # create what's missing
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass

from scripts import seed_calendar, seed_github, seed_sharepoint


@dataclass(frozen=True)
class Resource:
    name: str
    audit: Callable[[], dict[str, object]]
    apply: Callable[[], None]


RESOURCES: tuple[Resource, ...] = (
    Resource("github", seed_github.audit, seed_github.apply),
    Resource("outlook", seed_calendar.audit, seed_calendar.apply),
    Resource("sharepoint", seed_sharepoint.audit, seed_sharepoint.apply),
)


def _audit_one(resource: Resource) -> dict[str, object]:
    """Audit a single resource, mapping any error to a reported status (never raises)."""
    try:
        return resource.audit()
    except Exception as exc:  # surface, don't abort the whole audit
        return {"ready": True, "present": False, "detail": f"audit error: {exc}", "error": True}


def _status_word(status: dict[str, object]) -> str:
    if not status.get("ready"):
        return "— skipped"
    if status.get("error"):
        return "! error"
    return "✓ present" if status.get("present") else "✗ missing"


def _print_table(rows: list[tuple[Resource, dict[str, object]]]) -> None:
    print(f"\n{'RESOURCE':<12}{'CREDS':<8}{'STATUS':<12}DETAIL")
    print("-" * 72)
    for resource, status in rows:
        creds = "yes" if status.get("ready") else "no"
        print(f"{resource.name:<12}{creds:<8}{_status_word(status):<12}{status.get('detail', '')}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit (and optionally create) demo resources.")
    parser.add_argument("--apply", action="store_true", help="create the missing resources")
    parser.add_argument(
        "--force", action="store_true", help="with --apply, reseed even resources already present"
    )
    args = parser.parse_args()

    print("Auditing demo resources (read-only)…")
    rows = [(r, _audit_one(r)) for r in RESOURCES]
    _print_table(rows)

    ready = [(r, s) for r, s in rows if s.get("ready") and not s.get("error")]
    missing = [(r, s) for r, s in ready if not s.get("present")]
    skipped = [r for r, s in rows if not s.get("ready")]

    if not args.apply:
        if missing:
            names = ", ".join(r.name for r, _ in missing)
            print(f"Missing: {names}. Re-run with --apply to create them.")
        elif not skipped and all(s.get("present") for _, s in ready):
            print("All configured resources are present — the demo is ready.")
        if skipped:
            print(f"Skipped (no credentials): {', '.join(r.name for r in skipped)}.")
        return

    todo = ready if args.force else missing
    if not todo:
        print("Nothing to create — all configured resources are already present.")
    else:
        print(f"Applying: {', '.join(r.name for r, _ in todo)}…\n")
        for resource, _ in todo:
            print(f"--- {resource.name} ---")
            resource.apply()
        print("\nRe-auditing…")
        _print_table([(r, _audit_one(r)) for r, _ in todo])

    if skipped:
        print(f"Skipped (no credentials): {', '.join(r.name for r in skipped)}.")


if __name__ == "__main__":
    main()
