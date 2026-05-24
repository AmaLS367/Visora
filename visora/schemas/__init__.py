from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

class BaseToolResult(BaseModel):
    """Base class for all Visora tool outputs to ensure consistent structure."""
    success: bool = Field(..., description="Indicates if the operation was successful")
    error: Optional[str] = Field(None, description="Error message if the operation failed, otherwise None")

class ScreenshotResult(BaseToolResult):
    """Result schema for the screenshot capture tool."""
    image_base64: Optional[str] = Field(None, description="Base64 encoded PNG/JPEG image data")
    width: Optional[int] = Field(None, description="Width of the captured screenshot in pixels")
    height: Optional[int] = Field(None, description="Height of the captured screenshot in pixels")

class ScreenPoint(BaseModel):
    """Represents a projected 2D screen point."""
    x: float = Field(..., description="Screen X coordinate")
    y: float = Field(..., description="Screen Y coordinate")
    z: float = Field(..., description="Depth / distance from camera")
    is_behind_camera: bool = Field(..., description="True if the world point is behind the camera viewport")

class ProjectWorldPointsResult(BaseToolResult):
    """Result schema for the world-to-screen projection tool."""
    screen_points: List[ScreenPoint] = Field(default_factory=list, description="List of projected screen coordinates")

class ClipInspectorResult(BaseToolResult):
    """Result schema for the animation clip inspector tool."""
    clip_name: Optional[str] = Field(None, description="Name of the inspected animation clip")
    length: Optional[float] = Field(None, description="Length of the animation clip in seconds")
    fps: Optional[float] = Field(None, description="Frame rate of the animation clip")
    loop_time: Optional[bool] = Field(None, description="Whether loopTime is enabled on the clip")
    curves_count: Optional[int] = Field(None, description="Number of animation curves in this clip")

class SkeletonMapperResult(BaseToolResult):
    """Result schema for the skeleton mapper tool."""
    is_valid: bool = Field(default=False, description="True if the skeleton mapping is valid/complete")
    mappings: Dict[str, str] = Field(default_factory=dict, description="Dictionary mapping bone names to their transform paths")
    missing_bones: List[str] = Field(default_factory=list, description="List of required bones that are missing from the mapping")

class SafeTransactionResult(BaseToolResult):
    """Result schema for safe editor transaction operations."""
    transaction_id: Optional[str] = Field(None, description="Unique identifier for the transaction")
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
    bounds_center: Optional[List[float]] = Field(None, description="Bounding box center coordinates [x, y, z]")
    bounds_size: Optional[List[float]] = Field(None, description="Bounding box size dimensions [x, y, z]")
    material_count: int = Field(default=0, description="Number of materials attached to the renderer")
    bone_count: int = Field(default=0, description="Number of bones bound to the skinned mesh renderer")
    is_sub_mesh_valid: bool = Field(default=True, description="True if all sub-meshes are valid and non-empty")
    warnings: List[str] = Field(default_factory=list, description="List of non-blocking diagnostic warning messages")

class QueueStatusResult(BaseToolResult):
    """Result schema for long-running ticket queue status and polling."""
    ticket_id: str = Field(..., description="Unique ticket identifier in the AnkleBreaker queue")
    status: str = Field(..., description="Queue execution status: pending, running, completed, failed")
    progress: float = Field(default=0.0, description="Normalized progress from 0.0 to 1.0")
    result: Optional[Any] = Field(None, description="The execution result if status is completed")
