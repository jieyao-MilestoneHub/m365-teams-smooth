"""Typed domain errors.

Adapter and SDK exceptions are mapped to these at the adapter boundary so that
integration-specific failures never leak into the agent, services, or API layers.
"""

from __future__ import annotations


class ChangeCourtError(Exception):
    """Base class for all domain-level errors."""


class NotFoundError(ChangeCourtError):
    """A requested entity (trial, change, or audit record) does not exist."""


class InvalidRequestError(ChangeCourtError):
    """A submitted request fails boundary validation (empty, oversized, malformed)."""


class CapabilityNotFoundError(ChangeCourtError):
    """A requested action has no matching registered capability (hallucination guard)."""


class UnsafeChangeError(ChangeCourtError):
    """A change violates a policy constraint and cannot be executed as requested."""


class IntegrationError(ChangeCourtError):
    """An adapter failed; wraps the underlying SDK error at the adapter boundary."""


class ConfigurationError(ChangeCourtError):
    """A configured real capability cannot be served — fail fast, never serve a substitute."""


class VerdictConflictError(ChangeCourtError):
    """A verdict conflicts with a previously recorded one for the same trial."""


class SeparationOfDutiesError(ChangeCourtError):
    """The verdict caster is the requester; separation of duties forbids self-approval."""


class UnauthorizedApproverError(ChangeCourtError):
    """The caster holds none of the roles the trial's quorum requires."""


class GraphTimeoutError(ChangeCourtError):
    """A graph run exceeded its wall-clock budget; the checkpoint is left intact and resumable."""


class LlmOutputError(ChangeCourtError):
    """A schema-constrained LLM response is unusable (truncated or refused by the model)."""
