"""Domain enumerations. String-valued for stable serialization in checkpoints and audit records."""

from __future__ import annotations

from enum import StrEnum


class RunMode(StrEnum):
    """Whether execution predicts effects (no side effects) or applies them."""

    DRY_RUN = "dry_run"
    LIVE = "live"


class RiskLevel(StrEnum):
    """Banded risk output of policy scoring."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ChangeStatus(StrEnum):
    """Lifecycle of a trial."""

    INTAKE = "intake"
    EVALUATING = "evaluating"
    AWAITING_VERDICT = "awaiting_verdict"
    EXECUTING = "executing"
    DONE = "done"
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
