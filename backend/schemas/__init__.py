from typing import Any

from pydantic import BaseModel, Field


class BaseToolResult(BaseModel):
    """Base class for all Visora tool outputs to ensure consistent structure."""

    success: bool = Field(..., description="Indicates if the operation was successful")
    error: str | None = Field(default=None, description="Error message if the operation failed, otherwise None")


class ScreenshotResult(BaseToolResult):
    """Result schema for the screenshot capture tool."""

    image_base64: str | None = Field(default=None, description="Base64 encoded PNG/JPEG image data")
    width: int | None = Field(default=None, description="Width of the captured screenshot in pixels")
    height: int | None = Field(default=None, description="Height of the captured screenshot in pixels")
    camera_name: str | None = Field(default=None, description="Unity camera used for the capture")
    image_format: str = Field(default="png", description="Screenshot image format")
    warnings: list[str] = Field(default_factory=list, description="Non-blocking screenshot warnings")


class VisualComparisonResult(BaseToolResult):
    """Result schema for screenshot visual comparison diagnostics."""

    same_dimensions: bool = Field(default=False, description="True when compared screenshots have matching dimensions")
    width: int | None = Field(default=None, description="Compared image width in pixels when dimensions match")
    height: int | None = Field(default=None, description="Compared image height in pixels when dimensions match")
    changed_pixel_ratio: float = Field(default=0.0, description="Ratio of pixels whose delta exceeded the threshold")
    mean_delta: float = Field(default=0.0, description="Mean per-channel absolute delta across all pixels")
    max_delta: int = Field(default=0, description="Largest per-channel absolute delta observed")
    changed_bounds: list[int] | None = Field(
        default=None,
        description="Bounding rectangle for changed pixels as [min_x, min_y, max_x, max_y]",
    )
    warnings: list[str] = Field(default_factory=list, description="Non-blocking comparison warnings")


class VisualCapture(BaseModel):
    """Single visual inspection capture returned by a higher-level scene inspection workflow."""

    mode: str = Field(..., description="Capture mode, such as game_camera or diagnostic_lit")
    image_base64: str = Field(..., description="Base64 encoded PNG image data")
    width: int = Field(..., description="Capture width in pixels")
    height: int = Field(..., description="Capture height in pixels")
    camera_name: str = Field(..., description="Camera used for this capture")
    image_format: str = Field(default="png", description="Capture image format")
    warnings: list[str] = Field(default_factory=list, description="Capture-specific warnings")


class VisualInspectionResult(BaseToolResult):
    """Result schema for multi-pass visual scene inspection."""

    subject_path: str | None = Field(default=None, description="Optional inspected scene object path")
    captures: list[VisualCapture] = Field(default_factory=list, description="Ordered visual captures for inspection")
    warnings: list[str] = Field(default_factory=list, description="Workflow-level warnings for agents")
    recommended_interpretation: str = Field(..., description="Text guidance for how agents should inspect the captures")


class ScreenPoint(BaseModel):
    """Represents a projected 2D screen point."""

    x: float = Field(..., description="Screen X coordinate")
    y: float = Field(..., description="Screen Y coordinate")
    z: float = Field(..., description="Depth / distance from camera")
    is_behind_camera: bool = Field(..., description="True if the world point is behind the camera viewport")


class ProjectWorldPointsResult(BaseToolResult):
    """Result schema for the world-to-screen projection tool."""

    screen_points: list[ScreenPoint] = Field(default_factory=list, description="List of projected screen coordinates")


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


class SafeTransactionResult(BaseToolResult):
    """Result schema for safe editor transaction operations."""

    transaction_id: str | None = Field(default=None, description="Unique identifier for the transaction")
    scene_saved: bool = Field(default=False, description="Whether the active scene was saved prior to execution")
    message: str = Field(..., description="Status message detailing the outcome of the transaction")


class PlayModeManagementResult(BaseToolResult):
    """Result schema for playmode state changes."""

    is_playing: bool = Field(..., description="Current playmode state after the tool execution")
    previous_state: bool = Field(..., description="Previous playmode state prior to the tool execution")
    message: str = Field(..., description="Status message detailing the playmode state change")


class SkinnedMeshDiagnosticsResult(BaseToolResult):
    """Result schema for skinned mesh diagnostics."""

    has_bounds_issue: bool = Field(default=False, description="True if the mesh bounds are off-screen or zero-sized")
    bounds_center: list[float] | None = Field(default=None, description="Bounding box center coordinates [x, y, z]")
    bounds_size: list[float] | None = Field(default=None, description="Bounding box size dimensions [x, y, z]")
    material_count: int = Field(default=0, description="Number of materials attached to the renderer")
    bone_count: int = Field(default=0, description="Number of bones bound to the skinned mesh renderer")
    is_sub_mesh_valid: bool = Field(default=True, description="True if all sub-meshes are valid and non-empty")
    warnings: list[str] = Field(default_factory=list, description="List of non-blocking diagnostic warning messages")


class QueueStatusResult(BaseToolResult):
    """Result schema for long-running ticket queue status and polling."""

    ticket_id: str = Field(..., description="Unique ticket identifier in the AnkleBreaker queue")
    status: str = Field(..., description="Queue execution status: pending, running, completed, failed")
    progress: float = Field(default=0.0, description="Normalized progress from 0.0 to 1.0")
    result: Any | None = Field(default=None, description="The execution result if status is completed")
