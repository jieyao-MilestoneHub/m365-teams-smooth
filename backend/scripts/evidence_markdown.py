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

# Quorum roles are stored as machine identifiers; render them as the words an approver reads.
_ROLE_LABELS = {
    "eng_lead": "engineering lead",
    "security_lead": "security lead",
    "account_owner": "account owner",
    "manager": "manager",
    "comms": "communications",
}

# A citation is "<policy document> — <section heading>"; the document and heading split on this.
_CITATION_SEP = " — "


def _section(lines: list[str], title: str, rows: list[str]) -> None:
    if rows:
        lines.append(f"**{title}**")
        lines.extend(rows)
        lines.append("")


def _humanize_factor(label: object) -> str:
    """A risk factor's machine label as a readable phrase: ``target_date_conflict`` → ``Target date
    conflict``. Already-readable labels (spaces, capitals) pass through sentence-cased."""
    text = str(label).replace("_", " ").strip()
    return text[:1].upper() + text[1:] if text else ""


def _role_label(role: object) -> str:
    """An approver role identifier as the words an approver reads."""
    key = str(role)
    return _ROLE_LABELS.get(key, key.replace("_", " "))


def _policy_basis(factors: list[object]) -> list[str]:
    """The fired factors' citations, deduped once and grouped by policy document.

    Every factor carries the same trial-wide citation list, so rendering them per factor repeats
    the same policies on every line. Collapse to one section: dedupe across factors in order, then
    nest each cited section heading under its policy document.
    """
    groups: dict[str, list[str]] = {}
    for factor in factors:
        if not isinstance(factor, dict):
            continue
        for citation in factor.get("citations", []) or []:
            doc, _, clause = str(citation).partition(_CITATION_SEP)
            clauses = groups.setdefault(doc, [])
            if clause and clause not in clauses:
                clauses.append(clause)
    rows: list[str] = []
    for doc, clauses in groups.items():
        rows.append(f"- {doc}")
        rows.extend(f"  - {clause}" for clause in clauses)
    return rows


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
        level = str(risk.get("level", "")).lower()
        lines.append(f"**Risk:** {level.upper()} — {gate}")
        lines.append("")
        factors = risk.get("factors")
        factors = factors if isinstance(factors, list) else []
        # Prefer the gatherer's reader-facing drivers (its own grouping of the findings); fall back
        # to the factor labels. Either way the per-factor severities are left to the run page, so
        # the comment reads as evidence, not a classification table.
        impact = packet.get("impact")
        authored = impact.get("drivers") if isinstance(impact, dict) else None
        why = (
            [f"- {driver}" for driver in authored]
            if authored
            else [f"- {_humanize_factor(f.get('label'))}" for f in factors if isinstance(f, dict)]
        )
        _section(lines, f"Why this is {level} risk", why)
        _section(lines, "Policy basis", _policy_basis(factors))

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
        _section(lines, "Evidence", rows)

    plan = packet.get("plan")
    if isinstance(plan, dict):
        kind = "Safer alternative" if plan.get("kind") == "safe_alternative" else "Proposed plan"
        rows = []
        steps = plan.get("steps")
        if isinstance(steps, list):
            for step in steps:
                if isinstance(step, dict):
                    system = str(step.get("system", ""))
                    capability = str(step.get("capability", ""))
                    # Capability names may already carry their system prefix.
                    if not capability.startswith(f"{system}."):
                        capability = f"{system}.{capability}"
                    rows.append(f"- {capability}")
        lines.append(f"**{kind}:** {plan.get('rationale', '')}")
        lines.append("")
        _section(lines, "Steps", rows)

    quorum = packet.get("quorum")
    if isinstance(quorum, dict):
        roles = [_role_label(r) for r in quorum.get("required_roles", []) or []]
        if roles:
            heading = "Would-be approvers" if analysis_only else "Approvers required"
            lines.append(f"**{heading} ({quorum.get('policy')}):**")
            lines.extend(f"- {role}" for role in roles)
            lines.append("")

    if event == "decided":
        verdict = "approved" if packet.get("approved") else "rejected"
        lines.append(f"**Decision:** {verdict} by {packet.get('decider')} — {packet.get('note')}")
        lines.append("")

    if analysis_only:
        lines.append("_Analysis only — nothing executed._")
        lines.append("")

    run_url = packet.get("run_url")
    if run_url:
        lines.append(f"[View full risk assessment and audit]({run_url})")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
