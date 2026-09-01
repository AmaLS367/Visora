"""
Custom exceptions for the Visora Unity bridge layer.
Provides structured, typed errors for network, timeout, execution, and state failures.
"""

from typing import Any


class BridgeError(Exception):
    """Base exception for all Unity bridge errors."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class BridgeConnectionError(BridgeError):
    """Raised when the Unity Editor bridge is unreachable or connection is refused across candidate ports."""

    def __init__(
        self,
        message: str = "Unity bridge is not reachable on any configured port.",
        ports: list[int] | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, details)
        self.ports = ports or []


class BridgeTimeoutError(BridgeError):
    """Raised when a request, ticket polling, or editor operation times out."""

    def __init__(
        self,
        message: str = "Bridge operation timed out.",
        timeout_seconds: float | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, details)
        self.timeout_seconds = timeout_seconds


class BridgeHTTPError(BridgeError):
    """Raised when the Unity bridge returns an HTTP error status code."""

    def __init__(
        self,
        message: str,
        status_code: int,
        response_body: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, details)
        self.status_code = status_code
        self.response_body = response_body


class BridgeExecutionError(BridgeError):
    """Raised when Unity Editor dynamic script compilation or C# execution fails."""

    def __init__(
        self,
        message: str = "Unity Editor execution failed.",
        errors: list[str] | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, details)
        self.errors = errors or []


class BridgeStateError(BridgeError):
    """Raised when an operation cannot be performed in the current Editor state (e.g. Play mode vs Edit mode)."""

    def __init__(
        self,
        message: str = "Operation cannot be performed in the current Editor state.",
        current_state: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, details)
        self.current_state = current_state
