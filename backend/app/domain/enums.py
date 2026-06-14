"""Domain enumerations. String-valued for stable serialization in checkpoints and audit records."""

from __future__ import annotations

from enum import StrEnum


class RunMode(StrEnum):
    """Whether execution predicts effects (no side effects), applies them, or never happens."""

    DRY_RUN = "dry_run"
    LIVE = "live"
    # Impact check only: the pipeline gathers evidence, plans, and scores risk, then stops —
    # nothing executes regardless of risk level, and the run cannot be resumed into execution.
    ANALYZE = "analyze"


class RiskLevel(StrEnum):
    """Qualitative risk severity. A factor declares one; a trial's level is the highest that fired.

    Ordered low < medium < high via :attr:`rank` — the string values are not ordinally comparable,
    so policy takes the maximum by rank rather than relying on enum/string ordering.
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

    @property
    def rank(self) -> int:
        """Ordinal severity (low=0, medium=1, high=2), for taking the most severe fired factor."""
        return _RISK_RANK[self]


_RISK_RANK = {RiskLevel.LOW: 0, RiskLevel.MEDIUM: 1, RiskLevel.HIGH: 2}


class ChangeStatus(StrEnum):
    """Lifecycle of a trial."""

    INTAKE = "intake"
    EVALUATING = "evaluating"
    AWAITING_REQUESTER_REVIEW = "awaiting_requester_review"  # proposal built; requester reviews
    AWAITING_VERDICT = "awaiting_verdict"
    AWAITING_APPROVAL = "awaiting_approval"  # sent on; an authorized approver must decide
    EXECUTING = "executing"
    DONE = "done"
    ANALYZED = "analyzed"  # analysis-only run: evidence/plan/risk recorded, nothing executed
    REJECTED = "rejected"  # an approver rejected (with a note)
    WITHDRAWN = "withdrawn"  # the requester gave up before approval
    BLOCKED = "blocked"
    FAILED = "failed"


class CapabilityKind(StrEnum):
    """Read capabilities gather evidence; write capabilities mutate a system."""

    READ = "read"
    WRITE = "write"


class VerdictType(StrEnum):
    """The decisions a reviewer may cast."""

    APPROVE = "approve"
    APPROVE_INTERNAL_ONLY = "approve_internal_only"
    REQUEST_REVISION = "request_revision"
    REJECT = "reject"
    ACCEPT_ALTERNATIVE = "accept_alternative"
    WITHDRAW = "withdraw"  # requester abandons before approval (non-approving → execute skips)


class ApproverRole(StrEnum):
    """Roles a quorum can require."""

    ENG_LEAD = "eng_lead"
    SECURITY_LEAD = "security_lead"
    ACCOUNT_OWNER = "account_owner"
    MANAGER = "manager"
    COMMS = "comms"


class PlanKind(StrEnum):
    """Whether the plan fulfils the request or replaces it with a safer one."""

    FEASIBLE = "feasible"
    SAFE_ALTERNATIVE = "safe_alternative"


class StepStatus(StrEnum):
    """Outcome of a single execution step."""

    OK = "ok"
    FAILED = "failed"
    SKIPPED = "skipped"
    DRY_RUN = "dry_run"
