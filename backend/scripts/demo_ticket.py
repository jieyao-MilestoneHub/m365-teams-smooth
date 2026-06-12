"""Run the ticket demo: an analysis-only trial posts its evidence packet back to the ticket.

The driver for a ticket-first workflow: ``cd backend && uv run python -m scripts.demo_ticket``.
A change-request ticket already exists somewhere (a GitHub issue, an ITSM change); the court does
not replace it — it supplies the impact evidence the ticket is missing, in two acts:

- **Act 1 — the evidence packet.** The headline reschedule and one routine request run in
  ``run_mode=analyze``: the pipeline gathers evidence, plans, and scores risk, then stops —
  nothing executes — and the ``analyzed`` packet (risk factors with citations, impact evidence,
  the plan or safer alternative, the would-be approvers, the run link) is delivered through the
  evidence webhook. Routine work shows zero would-be approvers.
- **Act 2 — escalation on the evidence.** The high-risk change is resubmitted into the court's
  own gate (dry-run); the same webhook posts ``approval_requested`` and the ``decided`` outcome
  to the same ticket. Skip with ``--analyze-only``.

With ``EVIDENCE_WEBHOOK_URL`` set, packets go to that endpoint — run the reference receiver
(``scripts.evidence_receiver``) there and they land as comments on a real GitHub issue. Without
it, an in-process capture server receives the webhook's real HTTP POSTs credential-free and the
script prints exactly what would land on the ticket.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from app.config import Settings
from app.container import build_court_service
from app.domain import ChangeStatus, RunMode
from app.services.court_service import CourtService
from scripts.demo_identities import APPROVER, DIRECTORY, REQUESTER
from scripts.evidence_markdown import render_markdown

# The ticket's content is the headline reschedule request (byte-identical to scripts.demo) plus
# one routine request, so the packets show both poles: a high-risk change with a would-be quorum,
# and routine work that would need no approver at all.
_TICKET_REQUEST = "move the launch rehearsal to 2026-06-22"
_ROUTINE_REQUEST = "create action items from standup"


class _CaptureHandler(BaseHTTPRequestHandler):
    """Records each webhook POST so the demo can show what would land on the ticket."""

    server: _CaptureServer

    def do_POST(self) -> None:  # noqa: N802 — http.server dispatches on this exact name
        length = int(self.headers.get("Content-Length", "0"))
        packet = json.loads(self.rfile.read(length))
        self.server.packets.append(packet)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        return  # keep the demo output to the court's own narration


class _CaptureServer(HTTPServer):
    """A loopback endpoint standing in for the team's ticket system, credential-free."""

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), _CaptureHandler)
        self.packets: list[dict[str, object]] = []

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server_address[1]}/evidence"


def _show_new_packets(server: _CaptureServer | None, seen: int) -> int:
    """Print every packet received since ``seen`` as the ticket comment it would become."""
    if server is None:
        return seen
    for packet in server.packets[seen:]:
        print("\n  --- what lands on the ticket " + "-" * 40)
        for line in render_markdown(packet).rstrip().splitlines():
            print(f"  {line}")
        print("  " + "-" * 69)
    return len(server.packets)


def run(*, analyze_only: bool = False) -> list[dict[str, object]]:
    """Drive both acts; returns the captured packets (empty when an external URL is set)."""
    # The narration uses a few unicode glyphs; force UTF-8 so it never crashes on a legacy console.
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(encoding="utf-8")

    external_url = os.environ.get("EVIDENCE_WEBHOOK_URL", "").strip()
    server: _CaptureServer | None = None
    if external_url:
        url = external_url
        print(f"posting evidence packets to {url}")
    else:
        server = _CaptureServer()
        threading.Thread(target=server.serve_forever, daemon=True).start()
        url = server.url
        print("no EVIDENCE_WEBHOOK_URL set — capturing packets locally to show the ticket comment")

    service: CourtService = build_court_service(
        Settings(
            force_all_mock=True,
            db_url="sqlite:///:memory:",
            dry_run_default=True,
            approver_directory=DIRECTORY,
            evidence_webhook_url=url,
        )
    )
    seen = 0

    print("\n=== Act 1 — the evidence packet (analysis only, nothing executes) ===")
    for name, request in (
        ("Reschedule — hidden contractual breach", _TICKET_REQUEST),
        ("Meeting Actions — routine", _ROUTINE_REQUEST),
    ):
        print(f"\n--- {name} ---\n  > {request}")
        summary = service.submit_change(request, run_mode=RunMode.ANALYZE, requester=REQUESTER)
        gate = "would require approval" if summary.requires_approval else "zero approvers"
        print(f"  status={summary.status}  risk={summary.risk_level}  {gate}")
        seen = _show_new_packets(server, seen)

    if analyze_only:
        print("\nanalysis only — the ticket has its evidence; the court changed nothing.")
        if server is not None:
            server.shutdown()
        return list(server.packets) if server is not None else []

    print("\n=== Act 2 — escalation: the evidence demands an informed decision ===")
    print(f"  > {_TICKET_REQUEST}")
    summary = service.submit_change(_TICKET_REQUEST, requester=REQUESTER)
    summary = service.send_for_approval(
        summary.thread_id, actor=REQUESTER, note="please review — the evidence is attached"
    )
    print(f"  sent for approval: status={summary.status}")
    seen = _show_new_packets(server, seen)
    if summary.status == ChangeStatus.AWAITING_APPROVAL.value:
        decided = service.decide(
            summary.thread_id, actor=APPROVER, approve=True, note="approved on the evidence"
        )
        print(f"  decided by {APPROVER.display_name}: status={decided.status}")
        seen = _show_new_packets(server, seen)

    if server is not None:
        server.shutdown()
    return list(server.packets) if server is not None else []


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run the ticket demo (analysis-only evidence packet, then escalation)."
    )
    parser.add_argument(
        "--analyze-only",
        dest="analyze_only",
        action="store_true",
        help="stop after Act 1 — deliver the evidence packets and change nothing",
    )
    run(analyze_only=parser.parse_args().analyze_only)
