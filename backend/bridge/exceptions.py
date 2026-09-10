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


class BridgeProtocolError(BridgeError):
    """
    Raised when the bridge answers with HTTP success but not a usable JSON object.

    Unity does this while a domain reload is in flight: the HTTP listener is already up and returns
    200, but the body is empty or not yet JSON. Without a type of its own that surfaced as a raw
    JSONDecodeError, which callers waiting on a play mode transition could not recognise as the
    transient condition it is.
    """

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        content_type: str | None = None,
        body_preview: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, details)
        self.status_code = status_code
        self.content_type = content_type
        self.body_preview = body_preview


class BridgeBusyError(BridgeError):
    """
    Raised when a bridge request failed transiently (connection drop or mid-reload body) and Unity
    did not return to an idle state within `unity_bridge_ready_wait_seconds`.

    Surfaced instead of a bare timeout so the caller - and, via the tool layer, the agent - knows
    the failure is transient and worth retrying. `reason` is one of "compiling", "updating",
    "reloading" (domain reload, bridge briefly down), or "unreachable" (no bridge port ever
    resolved). `retry_after_seconds` is a suggested wait before retrying.
    """

    def __init__(
        self,
        message: str = "Unity Editor is busy (compiling or reloading) and did not settle in time.",
        reason: str = "reloading",
        retry_after_seconds: float | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, details)
        self.reason = reason
        self.retry_after_seconds = retry_after_seconds


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
