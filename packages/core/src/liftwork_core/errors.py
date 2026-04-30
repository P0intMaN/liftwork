"""Domain exception hierarchy. API maps these to HTTP status codes."""

from __future__ import annotations


class LiftworkError(Exception):
    """Base class for all liftwork domain errors."""


class NotFoundError(LiftworkError):
    """A requested resource does not exist."""


class ConflictError(LiftworkError):
    """Operation conflicts with current resource state."""


class ValidationError(LiftworkError):
    """Input failed business-rule validation (distinct from pydantic schema errors)."""


class AuthenticationError(LiftworkError):
    """Caller could not be authenticated."""


class AuthorizationError(LiftworkError):
    """Caller is authenticated but not permitted to perform the action."""


class ExternalServiceError(LiftworkError):
    """An external dependency (registry, k8s API, GitHub) failed."""
