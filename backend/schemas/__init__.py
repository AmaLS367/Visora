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


class SceneCameraInfo(BaseModel):
    """Compact metadata for a Unity scene camera."""

    name: str = Field(..., description="Unity camera GameObject name")
    path: str = Field(..., description="Hierarchy path to the camera GameObject")
    enabled: bool = Field(..., description="Whether the Camera component is enabled")
    active: bool = Field(..., description="Whether the camera GameObject is active in hierarchy")
    tag: str = Field(..., description="Camera GameObject tag")
    depth: float = Field(..., description="Camera rendering depth")
    field_of_view: float = Field(..., description="Perspective camera field of view")
    orthographic: bool = Field(..., description="Whether the camera is orthographic")
    orthographic_size: float = Field(..., description="Orthographic camera size")


class ScreenPoint(BaseModel):
    """Represents a projected 2D screen point."""

    x: float = Field(..., description="Screen X coordinate")
    y: float = Field(..., description="Screen Y coordinate")
    z: float = Field(..., description="Depth / distance from camera")
    is_behind_camera: bool = Field(..., description="True if the world point is behind the camera viewport")


class ProjectWorldPointsResult(BaseToolResult):
    """Result schema for the world-to-screen projection tool."""

    screen_points: list[ScreenPoint] = Field(default_factory=list, description="List of projected screen coordinates")


class CameraFramingDiagnosticsResult(BaseToolResult):
    """Result schema for checking whether a subject is framed by a Unity camera."""

    subject_path: str = Field(..., description="Inspected scene object path")
    camera_name: str = Field(..., description="Camera used for framing diagnostics")
    viewport_bounds: list[float] | None = Field(
        default=None,
        description="Subject viewport bounds [min_x, min_y, max_x, max_y]",
    )
    visible_ratio: float = Field(default=0.0, description="Approximate fraction of subject viewport bounds visible")
    is_visible: bool = Field(default=False, description="True if any subject bounds are inside the viewport")
    is_behind_camera: bool = Field(
        default=False, description="True if all sampled subject bounds are behind the camera"
    )
    is_clipped: bool = Field(
        default=False, description="True if subject is clipped by near/far planes or viewport edges"
    )
    framing_status: str = Field(
        default="unknown", description="Framing status: centered, offscreen, too_small, too_large, clipped"
    )
    warnings: list[str] = Field(default_factory=list, description="Non-blocking framing diagnostic warnings")


class VideoFrame(BaseModel):
    """Single sampled frame from a camera sequence."""

    frame_index: int = Field(..., description="Zero-based frame index in the sampled sequence")
    timestamp_seconds: float = Field(..., description="Timestamp offset from capture start")
    camera_name: str = Field(..., description="Camera used for this frame")
    mode: str = Field(..., description="Capture mode, such as game_camera or diagnostic_lit")
    image_base64: str = Field(..., description="Base64 encoded PNG frame")
    width: int = Field(..., description="Frame width in pixels")
    height: int = Field(..., description="Frame height in pixels")
    warnings: list[str] = Field(default_factory=list, description="Frame-specific warnings")


class FrameMotionMetrics(BaseModel):
    """Pixel-diff motion metrics between two adjacent sampled frames."""

    from_frame: int = Field(..., description="Source frame index")
    to_frame: int = Field(..., description="Target frame index")
    changed_pixel_ratio: float = Field(..., description="Ratio of changed pixels")
    mean_delta: float = Field(..., description="Mean per-channel absolute delta")
    max_delta: int = Field(..., description="Largest per-channel absolute delta")
    changed_bounds: list[int] | None = Field(
        default=None, description="Changed pixel bounds [min_x, min_y, max_x, max_y]"
    )


class VideoFrameSequence(BaseModel):
    """Sampled frame sequence for one camera and capture mode."""

    camera_name: str = Field(..., description="Camera used for this sequence")
    mode: str = Field(..., description="Capture mode")
    duration_seconds: float = Field(..., description="Requested capture duration")
    fps: int = Field(..., description="Requested frame sampling rate")
    frames: list[VideoFrame] = Field(default_factory=list, description="Sampled PNG frames")
    motion_metrics: list[FrameMotionMetrics] = Field(default_factory=list, description="Adjacent-frame motion metrics")
    warnings: list[str] = Field(default_factory=list, description="Sequence-level warnings")


class VideoFramesResult(BaseToolResult):
    """Result schema for sampled camera frame sequences."""

    sequences: list[VideoFrameSequence] = Field(default_factory=list, description="Captured camera frame sequences")
    warnings: list[str] = Field(default_factory=list, description="Workflow-level warnings")
    recommended_interpretation: str = Field(..., description="Text guidance for how agents should inspect frames")


class VideoMp4Result(BaseToolResult):
    """Result schema for MP4 video export from sampled camera frames."""

    video_base64: str | None = Field(default=None, description="Base64 encoded MP4 bytes")
    artifact_path: str | None = Field(default=None, description="Local artifact path for the MP4 file")
    format: str = Field(default="mp4", description="Video container format")
    camera_name: str = Field(..., description="Camera used for the video")
    mode: str = Field(..., description="Capture mode")
    duration_seconds: float = Field(..., description="Requested capture duration")
    fps: int = Field(..., description="Requested video frame rate")
    width: int = Field(..., description="Video width in pixels")
    height: int = Field(..., description="Video height in pixels")
    warnings: list[str] = Field(default_factory=list, description="Video export warnings")


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
