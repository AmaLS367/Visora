from pydantic import BaseModel, Field

from backend.schemas.animation import (
    AnimationPreviewKeyFrame,
    AnimationPreviewMotionSummary,
)
from backend.schemas.base import BaseToolResult


class PreviewSceneInfo(BaseModel):
    """Information about the Unity scene at the time of preview."""

    scene_path: str | None = Field(default=None, description="Active Unity scene asset path")
    scene_name: str | None = Field(default=None, description="Active scene name")
    is_dirty: bool = Field(default=False, description="Whether the scene was modified before preview")


class PreviewClipInfo(BaseModel):
    """Metadata and diagnostics for the AnimationClip being previewed."""

    clip_path: str = Field(..., description="AnimationClip asset path or name")
    clip_name: str | None = Field(default=None, description="Resolved clip name")
    length: float = Field(default=0.0, description="Total clip duration in seconds")
    loop_time: bool = Field(default=False, description="Whether the clip loops")
    event_count: int = Field(default=0, description="Number of animation events on this clip")
    dangerous_curves: list[str] = Field(
        default_factory=list, description="Descriptions of suspicious or dangerous curves"
    )


class PreviewCameraInfo(BaseModel):
    """Camera configuration and framing status during preview capture."""

    requested_camera_name: str = Field(..., description="Camera requested by caller")
    rendered_camera_name: str = Field(..., description="Actual camera rendered through")
    auto_frame_status: str = Field(
        default="disabled",
        description="Auto-frame status: applied, not_needed, disabled, unsupported, or failed",
    )
    framing_status_before: str | None = Field(
        default=None,
        description="Framing status before auto-framing: visible, clipped, off_screen, behind_camera, etc.",
    )


class PreviewCaptureSettings(BaseModel):
    """Requested and achieved capture parameters."""

    requested_start_time: float = Field(default=0.0, description="Requested start time in seconds")
    requested_end_time: float = Field(default=0.0, description="Requested end time in seconds")
    requested_fps: int = Field(default=24, description="Requested sampling frame rate")
    effective_fps: float = Field(default=24.0, description="Target frame rate after ceiling application")
    actual_fps: float | None = Field(default=None, description="Measured frame rate from returned timestamps")
    width: int = Field(default=640, description="Frame width in pixels")
    height: int = Field(default=360, description="Frame height in pixels")
    frame_ceiling_applied: bool = Field(default=False, description="Whether frame rate ceiling was enforced")
    range_truncated: bool = Field(default=False, description="Whether preview time range was truncated")
    timing_source: str = Field(default="edit_mode_sampled", description="Timing source reported by Unity")
    frame_count: int = Field(default=0, description="Total frames captured")


class PreviewEditorState(BaseModel):
    """Unity editor and bridge state captured at preview time."""

    is_playing: bool = Field(default=False, description="Whether Unity was in Play Mode")
    is_paused: bool = Field(default=False, description="Whether Unity was paused")
    pose_restored: bool = Field(default=True, description="Whether target pose was confirmed restored")
    scene_dirtied_by_preview: bool = Field(default=False, description="Whether sampling marked the scene modified")
    preview_camera_created: bool = Field(default=False, description="Whether temporary camera was spawned")
    preview_camera_destroyed: bool | None = Field(default=None, description="Whether temporary camera was cleaned up")


class PreviewActionMarker(BaseModel):
    """Named action event or motion beat within the clip timeline."""

    time: float = Field(..., description="Timestamp in seconds")
    label: str = Field(..., description="Action name or event label")
    marker_type: str = Field(
        default="event", description="Marker type: event, peak_motion, keyframe, impact, or custom"
    )


class PreviewArtifactFiles(BaseModel):
    """Paths to all persisted artifact files on disk for this preview."""

    record_path: str = Field(..., description="Path to this preview record JSON manifest")
    mp4_path: str | None = Field(default=None, description="Path to encoded MP4 preview video")
    contact_sheet_path: str | None = Field(default=None, description="Path to contact sheet PNG")
    key_frame_paths: list[str] = Field(default_factory=list, description="Paths to individual extracted keyframe PNGs")


class AnimationPreviewRecord(BaseModel):
    """Complete, reproducible manifest for an animation preview run."""

    preview_id: str = Field(..., description="Unique, stable preview identifier (e.g. prev_20260910_111800_ab12cd34)")
    created_at: str = Field(..., description="ISO 8601 UTC creation timestamp")
    target_object_path: str = Field(..., description="Scene hierarchy path of animated GameObject")
    scene: PreviewSceneInfo = Field(default_factory=PreviewSceneInfo)
    clip: PreviewClipInfo
    camera: PreviewCameraInfo
    capture_settings: PreviewCaptureSettings
    editor_state: PreviewEditorState
    action_markers: list[PreviewActionMarker] = Field(default_factory=list)
    artifacts: PreviewArtifactFiles
    motion_summary: AnimationPreviewMotionSummary | None = None
    motion_timeline: list[float] = Field(default_factory=list)
    key_frames: list[AnimationPreviewKeyFrame] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    recommended_interpretation: str = Field(default="")


class AnimationPreviewRecordSummary(BaseModel):
    """Compact summary of a preview record for listing tools."""

    preview_id: str = Field(..., description="Preview identifier")
    created_at: str = Field(..., description="ISO 8601 UTC creation timestamp")
    target_object_path: str = Field(..., description="Target GameObject hierarchy path")
    clip_path: str = Field(..., description="AnimationClip asset path")
    clip_name: str | None = Field(default=None, description="Resolved clip name")
    camera_name: str = Field(..., description="Camera used")
    frame_count: int = Field(default=0, description="Captured frame count")
    duration: float = Field(default=0.0, description="Preview duration in seconds")
    is_static: bool = Field(default=False, description="Whether near-zero motion was detected")
    mp4_path: str | None = Field(default=None, description="Path to MP4 preview video")
    record_path: str = Field(..., description="Path to preview record JSON file")


class AnimationPreviewRecordResult(BaseToolResult):
    """Result of querying an individual animation preview record."""

    record: AnimationPreviewRecord | None = Field(default=None, description="The loaded preview record")


class AnimationPreviewListResult(BaseToolResult):
    """Result of listing available animation preview records."""

    records: list[AnimationPreviewRecordSummary] = Field(
        default_factory=list, description="List of matching preview summaries"
    )
    total_count: int = Field(default=0, description="Total matching records found")


class AnimationPreviewInputsDiff(BaseModel):
    """Differences in input parameters and configuration between two previews."""

    clip_path_changed: bool = Field(default=False, description="Whether clip path differed")
    baseline_clip_path: str = Field(default="", description="Baseline clip path")
    comparison_clip_path: str = Field(default="", description="Comparison clip path")
    clip_length_delta: float = Field(default=0.0, description="Difference in clip length (comparison - baseline)")
    camera_changed: bool = Field(default=False, description="Whether camera differed")
    baseline_camera: str = Field(default="", description="Baseline camera")
    comparison_camera: str = Field(default="", description="Comparison camera")
    fps_delta: float = Field(default=0.0, description="Difference in effective sampling FPS")
    resolution_changed: bool = Field(default=False, description="Whether resolution differed")


class AnimationPreviewMotionDiff(BaseModel):
    """Differences in observed visual motion between two previews."""

    peak_motion_timestamp_delta: float | None = Field(
        default=None, description="Shift in peak motion timestamp (comparison - baseline)"
    )
    peak_changed_pixel_ratio_delta: float = Field(default=0.0, description="Change in peak visual motion intensity")
    mean_changed_pixel_ratio_delta: float = Field(default=0.0, description="Change in mean visual motion intensity")
    static_status_changed: bool = Field(default=False, description="Whether static/moving state transitioned")
    is_now_static: bool = Field(default=False, description="True if comparison became static")
    was_static: bool = Field(default=False, description="True if baseline was static")


class AnimationPreviewComparisonResult(BaseToolResult):
    """Result of comparing two animation preview runs to trace changes and detect regressions."""

    baseline_preview_id: str = Field(..., description="Identifier of baseline / before preview")
    comparison_preview_id: str = Field(..., description="Identifier of comparison / after preview")
    summary: str = Field(default="", description="Executive summary of improvements or regressions")
    inputs_diff: AnimationPreviewInputsDiff | None = Field(
        default=None, description="Deltas in preview input parameters and configuration"
    )
    motion_diff: AnimationPreviewMotionDiff | None = Field(
        default=None, description="Deltas in observed visual motion dynamics"
    )
    visual_comparison_sheet_path: str | None = Field(
        default=None, description="Path to side-by-side comparison artifact PNG"
    )
    events_diff: list[str] = Field(
        default_factory=list, description="Differences in animation events or action markers"
    )
    sliding_reduced_percent: float = Field(
        default=0.0, description="Percentage reduction in foot/effector sliding distance"
    )
    jerk_reduced_percent: float = Field(default=0.0, description="Percentage reduction in peak jerk (smoothness gain)")
    peak_speed_delta: float = Field(default=0.0, description="Delta in peak effector velocity in m/s")
    framing_distance_delta: float = Field(default=0.0, description="Delta in distance to camera lens in meters")
    keyframes_diff_count: int = Field(default=0, description="Count of keyframes modified, added, or removed")
    improvements: list[str] = Field(default_factory=list, description="Detected positive improvements")
    regression_warnings: list[str] = Field(default_factory=list, description="Identified regressions or quality drops")
