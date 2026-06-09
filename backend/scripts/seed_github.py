"""Seed the demo GitHub repo so the ``github:real`` evidence path reads a real milestone.

The Reschedule trial reads a milestone titled **Launch Rehearsal** and moves its due date; this
script ensures that milestone exists with the pre-trial due date. ``apply`` doubles as the
between-takes reset (the trial moves the date forward, this puts it back).

Idempotent: if the milestone exists its due date is reset; otherwise it is created. Requirements:
``GITHUB_TOKEN`` (Issues: read and write) and ``GITHUB_REPO`` (``owner/name``) — a throwaway repo.

Reusable by ``scripts.setup_demo`` via :func:`audit` (read-only presence check) and :func:`apply`
(idempotent create/reset).

Run:  ``cd backend && uv run python -m scripts.seed_github``  (``--dry-run`` = report only)
"""

from __future__ import annotations

import argparse
import os

import httpx

_API = "https://api.github.com"
_MILESTONE_TITLE = "Launch Rehearsal"
_PRE_TRIAL_DUE = "2026-06-10T00:00:00Z"


def _credentials_ready() -> bool:
    return bool(os.environ.get("GITHUB_TOKEN") and os.environ.get("GITHUB_REPO"))


def _client() -> httpx.Client:
    return httpx.Client(
        base_url=_API,
        timeout=30,
        headers={
            "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )


def _find_milestone(g: httpx.Client, repo: str) -> dict[str, object]:
    resp = g.get(f"/repos/{repo}/milestones", params={"state": "all", "per_page": "100"})
    resp.raise_for_status()
    return next((m for m in resp.json() if m.get("title") == _MILESTONE_TITLE), {})


def audit() -> dict[str, object]:
    """Read-only: does the ``Launch Rehearsal`` milestone exist? Never writes."""
    if not _credentials_ready():
        return {"ready": False, "present": False, "detail": "GITHUB_TOKEN/GITHUB_REPO unset"}
    repo = os.environ["GITHUB_REPO"]
    with _client() as g:
        milestone = _find_milestone(g, repo)
    if not milestone:
        return {
            "ready": True,
            "present": False,
            "detail": f"milestone '{_MILESTONE_TITLE}' missing in {repo}",
        }
    due = str(milestone.get("due_on") or "no due date")
    return {"ready": True, "present": True, "detail": f"'{_MILESTONE_TITLE}' in {repo} (due {due})"}


def apply() -> None:
    """Idempotent: reset the milestone's due date to the pre-trial date, or create it."""
    repo = os.environ["GITHUB_REPO"]
    with _client() as g:
        milestone = _find_milestone(g, repo)
        if milestone:
            number = milestone["number"]
            g.patch(
                f"/repos/{repo}/milestones/{number}",
                json={"due_on": _PRE_TRIAL_DUE, "state": "open"},
            ).raise_for_status()
            print(f"reset milestone '{_MILESTONE_TITLE}' (#{number}) due → {_PRE_TRIAL_DUE[:10]}")
        else:
            resp = g.post(
                f"/repos/{repo}/milestones",
                json={"title": _MILESTONE_TITLE, "due_on": _PRE_TRIAL_DUE, "state": "open"},
            )
            resp.raise_for_status()
            number = resp.json()["number"]
            print(f"created milestone '{_MILESTONE_TITLE}' (#{number}) due {_PRE_TRIAL_DUE[:10]}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the demo GitHub milestone.")
    parser.add_argument("--dry-run", action="store_true", help="report only, no writes")
    args = parser.parse_args()

    repo = os.environ.get("GITHUB_REPO", "<GITHUB_REPO unset>")
    print(f"repo: {repo}\nmilestone: {_MILESTONE_TITLE} (due {_PRE_TRIAL_DUE[:10]})")
    if args.dry_run:
        return

    apply()


if __name__ == "__main__":
    main()
