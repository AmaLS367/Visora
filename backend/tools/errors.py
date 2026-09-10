"""Shared translation of bridge exceptions into tool-result fields."""

from typing import Any

from backend.bridge import BridgeBusyError


def bridge_error(exc: BaseException) -> dict[str, Any]:
    """
    Failure fields for a tool whose bridge call raised. Spread into any `BaseToolResult`:

        return SomeResult(**bridge_error(exc), warnings=[...])

    A plain failure yields `success=False` and `error`. A `BridgeBusyError` (Unity was mid
    domain-reload or compiling) additionally sets `retryable=True`, `unity_state`, and
    `retry_after_seconds`, so the agent waits and retries instead of treating it as a hard failure.
    """
    fields: dict[str, Any] = {"success": False, "error": str(exc)}
    fields.update(bridge_retry_fields(exc))
    return fields


def bridge_retry_fields(exc: BaseException) -> dict[str, Any]:
    """
    Just the transient-retry fields (no `success` / `error`), for result builders and internal
    carriers that set the error string themselves. Empty unless `exc` is a `BridgeBusyError`.
    Never flags 'unreachable' as retryable to prevent infinite retry loops when Unity is not running.
    """
    if isinstance(exc, BridgeBusyError) and exc.reason != "unreachable":
        return {"retryable": True, "unity_state": exc.reason, "retry_after_seconds": exc.retry_after_seconds}
    return {}
