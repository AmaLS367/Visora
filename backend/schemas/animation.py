from pydantic import Field

from backend.schemas.base import BaseToolResult


class ClipInspectorResult(BaseToolResult):
    """Result schema for the animation clip inspector tool."""

    clip_name: str | None = Field(default=None, description="Name of the inspected animation clip")
    length: float | None = Field(default=None, description="Length of the animation clip in seconds")
    fps: float | None = Field(default=None, description="Frame rate of the animation clip")
    loop_time: bool | None = Field(default=None, description="Whether loopTime is enabled on the clip")
    curves_count: int | None = Field(default=None, description="Number of animation curves in this clip")


class SkeletonMapperResult(BaseToolResult):
    """Result schema for the skeleton mapper tool."""

    is_valid: bool = Field(default=False, description="True if the skeleton mapping is valid/complete")
    mappings: dict[str, str] = Field(
        default_factory=dict,
        description="Dictionary mapping bone names to their transform paths",
    )
    missing_bones: list[str] = Field(
        default_factory=list,
        description="List of required bones that are missing from the mapping",
    )
