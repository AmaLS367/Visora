from pydantic import BaseModel, Field


class RetryHint(BaseModel):
    """
    Transient-failure hint fields, mixed into tool results.

    Set together (via `backend.tools.errors.bridge_error`) when a call failed because Unity was
    mid domain-reload or compiling, so the agent waits and retries instead of treating it as a
    hard failure.
    """

    retryable: bool = Field(
        default=False,
        description="True when the failure is transient (Unity was mid domain-reload or compiling) "
        "and the identical call is worth retrying once the editor settles",
    )
    unity_state: str | None = Field(
        default=None,
        description="When retryable: what Unity was doing - 'compiling', 'updating', 'reloading', or 'unreachable'",
    )
    retry_after_seconds: float | None = Field(
        default=None, description="When retryable: suggested wait in seconds before retrying"
    )


class BaseToolResult(RetryHint):
    """Base class for all Visora tool outputs to ensure consistent structure."""

    success: bool = Field(..., description="Indicates if the operation was successful")
    error: str | None = Field(default=None, description="Error message if the operation failed, otherwise None")
