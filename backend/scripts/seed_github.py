"""Seed the demo GitHub repo so the ``github:real`` evidence path reads real milestones.

The Reschedule trial reads a milestone titled **Launch Rehearsal** and moves its due date, and its
breach evidence traverses the dependent **Customer Go-Live** milestone (the dependency is declared
in that milestone's description — ``depends_on`` / ``required_buffer_days`` — which the real
adapter parses). This script ensures both exist with the pre-trial dates. It also owns the demo
**change ticket** — the open issue the evidence receiver
(``scripts/evidence_receiver.py``) posts the trial's analysis onto; ``apply`` prints its number to
set as ``EVIDENCE_ISSUE``. ``apply`` doubles as the between-takes reset: the milestone date goes
back to its seeded state, and the ticket's prior Change Court evidence comments are removed.

Idempotent: an existing milestone is reset to its seeded state; a missing one is created; the
ticket is created once, reopened if closed, and only comments carrying the receiver's marker are
ever deleted. Requirements: ``GITHUB_TOKEN`` (Issues: read and write) and ``GITHUB_REPO``
(``owner/name``).

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

# The seeded milestones. Customer Go-Live's description carries the dependency convention the
# real adapter's read_milestone_dependencies parses; the 5-day buffer before its 2026-06-26 due
# date mirrors the mock, so a 2026-06-22 rehearsal compresses it in real mode too.
_MILESTONES: tuple[dict[str, str], ...] = (
    {"title": _MILESTONE_TITLE, "due_on": _PRE_TRIAL_DUE},
    {
        "title": "Customer Go-Live",
        "due_on": "2026-06-26T00:00:00Z",
        "description": (
            "Customer A production go-live.\n"
            "depends_on: Launch Rehearsal\n"
            "required_buffer_days: 5"
        ),
    },
)


# The demo change ticket: the existing issue a ticket-first team would already have. The evidence
# receiver lands the court's analysis on it as comments, each starting with the marker below — the
# only comments the between-takes reset is allowed to delete.
_ISSUE_TITLE = "Change request: move the launch rehearsal"
_ISSUE_BODY = (
    "Requested: move the launch rehearsal.\n\n"
    "This is the demo's change ticket: when the change is sent for approval, the Change Court "
    "evidence receiver posts the cross-system analysis below as a comment."
)
_EVIDENCE_MARKER = "### Change Court —"


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


def _find_milestone(g: httpx.Client, repo: str, title: str) -> dict[str, object]:
    resp = g.get(f"/repos/{repo}/milestones", params={"state": "all", "per_page": "100"})
    resp.raise_for_status()
    return next((m for m in resp.json() if m.get("title") == title), {})


def _find_issue(g: httpx.Client, repo: str, title: str) -> dict[str, object]:
    resp = g.get(f"/repos/{repo}/issues", params={"state": "all", "per_page": "100"})
    resp.raise_for_status()
    return next(
        (i for i in resp.json() if i.get("title") == title and "pull_request" not in i), {}
    )


def audit() -> dict[str, object]:
    """Read-only: do the seeded milestones and the demo change ticket exist? Never writes."""
    if not _credentials_ready():
        return {"ready": False, "present": False, "detail": "GITHUB_TOKEN/GITHUB_REPO unset"}
    repo = os.environ["GITHUB_REPO"]
    found: list[str] = []
    missing: list[str] = []
    with _client() as g:
        for spec in _MILESTONES:
            milestone = _find_milestone(g, repo, spec["title"])
            if milestone:
                due = str(milestone.get("due_on") or "no due date")
                found.append(f"'{spec['title']}' (due {due})")
            else:
                missing.append(f"'{spec['title']}'")
        issue = _find_issue(g, repo, _ISSUE_TITLE)
        if issue:
            found.append(f"ticket '{_ISSUE_TITLE}' (#{issue['number']}, {issue['state']})")
        else:
            missing.append(f"ticket '{_ISSUE_TITLE}'")
    if missing:
        return {
            "ready": True,
            "present": False,
            "detail": f"missing in {repo}: {', '.join(missing)}",
        }
    return {"ready": True, "present": True, "detail": f"{', '.join(found)} in {repo}"}


def apply() -> None:
    """Idempotent: reset each milestone to its seeded state, or create it."""
    repo = os.environ["GITHUB_REPO"]
    with _client() as g:
        for spec in _MILESTONES:
            payload: dict[str, str] = {"due_on": spec["due_on"], "state": "open"}
            if "description" in spec:
                payload["description"] = spec["description"]
            milestone = _find_milestone(g, repo, spec["title"])
            if milestone:
                number = milestone["number"]
                g.patch(f"/repos/{repo}/milestones/{number}", json=payload).raise_for_status()
                print(f"reset milestone '{spec['title']}' (#{number}) due → {spec['due_on'][:10]}")
            else:
                resp = g.post(
                    f"/repos/{repo}/milestones", json={"title": spec["title"], **payload}
                )
                resp.raise_for_status()
                number = resp.json()["number"]
                # GitHub normalizes due_on to the owner's timezone on CREATION (a midnight-UTC
                # date can land on the previous day); a follow-up PATCH stores it verbatim.
                g.patch(f"/repos/{repo}/milestones/{number}", json=payload).raise_for_status()
                print(f"created milestone '{spec['title']}' (#{number}) due {spec['due_on'][:10]}")
        _apply_ticket(g, repo)


def _apply_ticket(g: httpx.Client, repo: str) -> None:
    """Create or reopen the demo change ticket, and clear its prior evidence comments."""
    issue = _find_issue(g, repo, _ISSUE_TITLE)
    if not issue:
        resp = g.post(f"/repos/{repo}/issues", json={"title": _ISSUE_TITLE, "body": _ISSUE_BODY})
        resp.raise_for_status()
        number = int(resp.json()["number"])
        print(f"created ticket '{_ISSUE_TITLE}' (#{number})")
    else:
        number = int(str(issue["number"]))
        if issue.get("state") != "open":
            g.patch(f"/repos/{repo}/issues/{number}", json={"state": "open"}).raise_for_status()
            print(f"reopened ticket '{_ISSUE_TITLE}' (#{number})")
        resp = g.get(f"/repos/{repo}/issues/{number}/comments", params={"per_page": "100"})
        resp.raise_for_status()
        stale = [c for c in resp.json() if str(c.get("body", "")).startswith(_EVIDENCE_MARKER)]
        for comment in stale:
            g.delete(f"/repos/{repo}/issues/comments/{comment['id']}").raise_for_status()
        if stale:
            print(f"removed {len(stale)} prior evidence comment(s) from #{number}")
    print(f"evidence receiver target: EVIDENCE_ISSUE={number}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the demo GitHub milestone.")
    parser.add_argument("--dry-run", action="store_true", help="report only, no writes")
    args = parser.parse_args()

    repo = os.environ.get("GITHUB_REPO", "<GITHUB_REPO unset>")
    print(f"repo: {repo}")
    for spec in _MILESTONES:
        print(f"  milestone: {spec['title']} (due {spec['due_on'][:10]})")
    print(f"  ticket: {_ISSUE_TITLE}")
    if args.dry_run:
        return

    apply()


if __name__ == "__main__":
    main()
