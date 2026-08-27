"""ARC — public exception hierarchy.

Every error the SDK raises derives from :class:`ARCError`, so downstream
applications can catch the whole surface with a single ``except`` clause while
still being able to discriminate specific failure modes when needed.

This module contains no runtime logic; it only declares the contract.
"""

from __future__ import annotations

from typing import Any, List, Optional


class ARCError(Exception):
    """Base class for every exception raised by the ARC SDK."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ConfigurationError(ARCError):
    """Raised when the SDK is constructed or configured with invalid options."""


class APIError(ARCError):
    """Raised when the ARC control plane returns a non-success HTTP status."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        response_body: Optional[Any] = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class APIConnectionError(ARCError):
    """Raised when the SDK cannot reach the ARC control plane."""

    def __init__(self, message: str, cause: Optional[BaseException] = None) -> None:
        super().__init__(message)
        self.cause = cause
        if cause is not None:
            self.__cause__ = cause


class AuthenticationError(APIError):
    """Raised on ``401``/``403`` responses from the control plane."""


class NotFoundError(APIError):
    """Raised when a requested session, trace, or checkpoint does not exist."""


class ServerError(APIError):
    """Raised when the control plane returns a ``5xx`` response."""


class VerificationError(ARCError):
    """Raised when a policy/compliance verification fails."""

    def __init__(self, message: str, conflicts: Optional[List[Any]] = None) -> None:
        super().__init__(message)
        self.conflicts = conflicts or []


class RecoveryError(ARCError):
    """Raised when checkpointing or rollback cannot complete."""


class MiddlewareError(ARCError):
    """Raised when a middleware is invalid or fails during registration."""


class PluginError(ARCError):
    """Raised when a plugin is invalid or fails during registration."""


__all__ = [
    "ARCError",
    "ConfigurationError",
    "APIError",
    "APIConnectionError",
    "AuthenticationError",
    "NotFoundError",
    "ServerError",
    "VerificationError",
    "RecoveryError",
    "MiddlewareError",
    "PluginError",
]