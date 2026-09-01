from pydantic import BaseModel, Field


class BaseToolResult(BaseModel):
    """Base class for all Visora tool outputs to ensure consistent structure."""

    success: bool = Field(..., description="Indicates if the operation was successful")
    error: str | None = Field(default=None, description="Error message if the operation failed, otherwise None")
