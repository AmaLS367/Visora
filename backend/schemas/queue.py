from typing import Any

from pydantic import Field

from backend.schemas.base import BaseToolResult


class QueueStatusResult(BaseToolResult):
    """Result schema for long-running ticket queue status and polling."""

    ticket_id: str = Field(..., description="Unique ticket identifier in the AnkleBreaker queue")
    status: str = Field(..., description="Queue execution status: pending, running, completed, failed")
    progress: float = Field(default=0.0, description="Normalized progress from 0.0 to 1.0")
    result: Any | None = Field(default=None, description="The execution result if status is completed")
