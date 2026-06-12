"""Renders the court's evidence packet as one ticket comment in Markdown.

Pure presentation, importable with zero configuration: the reference receiver
(``scripts.evidence_receiver``) posts this rendering to a GitHub issue, and local tooling can
preview exactly what would land on a ticket without any credentials. The ``analyzed`` event is an
analysis-only conclusion — nothing executed and no one has decided — so its approval language is
conditional: the gate and the quorum are reported as what *would* happen if the change went on to
execution.
"""

from __future__ import annotations

_EVENT_TITLES = {
    "analyzed": "Impact analysis — nothing executed",
    "approval_requested": "Approval requested",
    "decided": "Decision recorded",
    "acknowledged": "Outcome acknowledged",
}


def _section(lines: list[str], title: str, rows: list[str]) -> None:
    if rows:
        lines.append(f"**{title}**")
        lines.extend(rows)
        lines.append("")


def render_markdown(packet: dict[str, object]) -> str:
    """The evidence packet as one ticket comment: decision context first, then the analysis."""
    event = str(packet.get("event", "event"))
    analysis_only = event == "analyzed"
    lines = [f"### Change Court — {_EVENT_TITLES.get(event, event)}", ""]

    change = packet.get("change")
    if isinstance(change, dict):
        lines.append(f"> {change.get('raw_request', '')}")
        lines.append("")

    risk = packet.get("risk")
    if isinstance(risk, dict):
        if analysis_only:
            gate = (
                "would require approval"
                if risk.get("requires_approval")
                else "would need no approver — the requester's confirmation would execute it"
            )
        else:
            gate = (
                "approval required"
                if risk.get("requires_approval")
                else "no approver required — the requester's confirmation executes it"
            )
        lines.append(f"**Risk:** {str(risk.get('level', '')).upper()} ({gate})")
        factors = risk.get("factors")
        rows = []
        if isinstance(factors, list):
            for factor in factors:
                if isinstance(factor, dict):
                    citations = ", ".join(str(c) for c in factor.get("citations", []) or [])
                    suffix = f" — {citations}" if citations else ""
                    rows.append(f"- {factor.get('label')} (+{factor.get('weight')}){suffix}")
        lines.append("")
        _section(lines, "Risk factors", rows)

    impact = packet.get("impact")
    if isinstance(impact, dict):
        rows = []
        items = impact.get("items")
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    rows.append(
                        f"- [{item.get('system')}] {item.get('summary')}"
                        f" ({item.get('severity')})"
                    )
        _section(lines, "Impact evidence", rows)

    plan = packet.get("plan")
    if isinstance(plan, dict):
        kind = "Safer alternative" if plan.get("kind") == "safe_alternative" else "Proposed plan"
        rows = []
        steps = plan.get("steps")
        if isinstance(steps, list):
            rows = [
                f"- {step.get('system')}.{step.get('capability')}"
                for step in steps
                if isinstance(step, dict)
            ]
        lines.append(f"**{kind}:** {plan.get('rationale', '')}")
        lines.append("")
        _section(lines, "Steps", rows)

    quorum = packet.get("quorum")
    if isinstance(quorum, dict):
        roles = ", ".join(str(r) for r in quorum.get("required_roles", []) or [])
        if roles:
            heading = "Would-be approvers" if analysis_only else "Approvers required"
            lines.append(f"**{heading} ({quorum.get('policy')}):** {roles}")
            lines.append("")

    if event == "decided":
        verdict = "approved" if packet.get("approved") else "rejected"
        lines.append(f"**Decision:** {verdict} by {packet.get('decider')} — {packet.get('note')}")
        lines.append("")

    run_url = packet.get("run_url")
    if run_url:
        lines.append(f"[View the full pipeline run]({run_url})")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
