from typing import Literal

from pydantic import BaseModel, Field

from backend.schemas.base import BaseToolResult


class MotionAnomaly(BaseModel):
    """Specific motion anomaly detected during high-order derivative analysis."""

    timestamp: float = Field(
        ...,
        description="Time (seconds) within the AnimationClip where the anomaly occurred",
    )
    bone_name: str = Field(
        ...,
        description="Name of the affected bone or transform",
    )
    anomaly_type: Literal["jerk_spike", "angular_jerk_spike", "velocity_snap", "arc_kink"] = Field(
        ...,
        description="Classification of the anomaly",
    )
    severity: Literal["critical", "warning"] = Field(
        ...,
        description="'critical' indicates severe popping or snapping; 'warning' indicates mild jitter",
    )
    metric_value: float = Field(
        ...,
        description="Measured value of the metric (e.g. jerk in m/s^3, angular jerk in deg/s^3)",
    )
    threshold: float = Field(
        ...,
        description="Threshold value that was exceeded",
    )
    description: str = Field(
        ...,
        description="Detailed diagnostic explanation of the anomaly",
    )
    recommendation: str = Field(
        ...,
        description="Actionable advice on how to smooth or correct the anomaly",
    )


class BoneMotionSummary(BaseModel):
    """Summary of kinematic metrics for an individual bone across the animation clip."""

    bone_name: str = Field(
        ...,
        description="Name of the evaluated bone",
    )
    peak_velocity: float = Field(
        ...,
        description="Maximum linear speed (m/s) observed across time",
    )
    peak_acceleration: float = Field(
        ...,
        description="Maximum linear acceleration (m/s^2)",
    )
    peak_jerk: float = Field(
        ...,
        description="Maximum rate of acceleration change (m/s^3)",
    )
    average_jerk: float = Field(
        ...,
        description="Mean jerk (m/s^3) over the clip duration",
    )
    smoothness_score: float = Field(
        ...,
        description="Smoothness score from 0.0 (erratic/snapping) to 1.0 (silky smooth)",
    )


class JointMotionAnalysisResult(BaseToolResult):
    """Result of temporal motion and jerk derivative analysis across an AnimationClip."""

    clip_path: str = Field(
        ...,
        description="Asset path to the analyzed AnimationClip",
    )
    target_object_path: str = Field(
        ...,
        description="Hierarchy path to the target GameObject in the scene",
    )
    clip_duration: float = Field(
        default=0.0,
        description="Duration of the clip in seconds",
    )
    sample_count: int = Field(
        default=0,
        description="Total number of discrete time samples evaluated",
    )
    sample_fps: float = Field(
        default=60.0,
        description="Sampling frequency (frames per second)",
    )
    overall_smoothness_score: float = Field(
        default=1.0,
        description="Aggregate smoothness score from 0.0 to 1.0 across all evaluated bones",
    )
    anomalies: list[MotionAnomaly] = Field(
        default_factory=list,
        description="List of detected motion anomalies (jerk spikes, velocity reversals, etc.)",
    )
    per_bone_summary: list[BoneMotionSummary] = Field(
        default_factory=list,
        description="Per-bone kinematics and smoothness summaries",
    )
    recommendations: list[str] = Field(
        default_factory=list,
        description="Concrete suggestions to improve motion flow and eliminate jitter",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Non-fatal warnings or diagnostic messages",
    )


class CurveDiscontinuityItem(BaseModel):
    """Specific curve defect detected (quaternion flip, Euler jump, tangent singularity)."""

    curve_path: str = Field(
        ...,
        description="Hierarchy path to the transform binding",
    )
    property_name: str = Field(
        ...,
        description="Property name (e.g. m_LocalRotation, localEulerAnglesRaw.x)",
    )
    timestamp: float = Field(
        ...,
        description="Timestamp (seconds) of the offending keyframe interval",
    )
    issue_type: Literal["quaternion_flip", "euler_wrap", "tangent_spike"] = Field(
        ...,
        description="Classification of the curve discontinuity",
    )
    severity: Literal["critical", "warning"] = Field(
        ...,
        description="'critical' causes 360° flips or camera snaps; 'warning' causes overshoots",
    )
    current_value: float = Field(
        ...,
        description="Measured metric value (e.g. 4D dot product for quaternion flips)",
    )
    description: str = Field(
        ...,
        description="Human-readable description of the curve defect",
    )
    suggested_fix: str = Field(
        ...,
        description="Actionable fix or confirmation that EnsureQuaternionContinuity resolves it",
    )


class CurveDiscontinuityResult(BaseToolResult):
    """Result of scanning AnimationClip curves for quaternion sign flips and tangent bugs."""

    clip_path: str = Field(
        ...,
        description="Asset path to the inspected AnimationClip",
    )
    discontinuities_count: int = Field(
        default=0,
        description="Total number of curve discontinuities detected",
    )
    items: list[CurveDiscontinuityItem] = Field(
        default_factory=list,
        description="Detailed list of detected curve issues",
    )
    fix_applied: bool = Field(
        default=False,
        description="True if auto_fix was requested and applied with pre-mutation backup",
    )
    backup_id: str | None = Field(
        default=None,
        description="Pre-mutation backup identifier under VisoraBackups/ if auto_fix was applied",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Non-fatal warnings or diagnostic messages",
    )


class AnimationComparisonResult(BaseToolResult):
    """Result of comparing two animation preview runs or clip evaluations."""

    baseline_preview_id: str = Field(
        ...,
        description="Identifier of the baseline / before preview",
    )
    comparison_preview_id: str = Field(
        ...,
        description="Identifier of the comparison / after preview",
    )
    summary: str = Field(
        default="",
        description="Executive summary of improvements or regressions observed between the runs",
    )
    sliding_reduced_percent: float = Field(
        default=0.0,
        description="Percentage reduction in foot/effector sliding distance (positive is improvement)",
    )
    jerk_reduced_percent: float = Field(
        default=0.0,
        description="Percentage reduction in peak jerk (positive is smoother motion)",
    )
    peak_speed_delta: float = Field(
        default=0.0,
        description="Delta in peak effector velocity (after - before) in m/s",
    )
    framing_distance_delta: float = Field(
        default=0.0,
        description="Delta in distance to camera lens (after - before) in meters",
    )
    keyframes_diff_count: int = Field(
        default=0,
        description="Count of keyframes modified, added, or removed between runs",
    )
    regression_warnings: list[str] = Field(
        default_factory=list,
        description="Identified regressions (e.g. increased ground penetration or new jerk spikes)",
    )
