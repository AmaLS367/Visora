from typing import Any

import backend.tools.animation as animation_pkg
from backend.app import mcp
from backend.schemas import (
    AnimationComparisonResult,
    BoneMotionSummary,
    CurveDiscontinuityItem,
    CurveDiscontinuityResult,
    JointMotionAnalysisResult,
    MotionAnomaly,
)
from backend.tools.animation.common import _bridge_supports, _require_edit_mode, logger

_CAPABILITY_MOTION_QA = "animation_motion_qa"
_CAPABILITY_CURVE_DISCONTINUITY = "curve_discontinuity_detection"


def _parse_anomalies(raw_list: list[Any]) -> list[MotionAnomaly]:
    anomalies: list[MotionAnomaly] = []
    for item in raw_list:
        if isinstance(item, dict):
            anomalies.append(
                MotionAnomaly(
                    timestamp=float(item.get("timestamp", 0.0)),
                    bone_name=str(item.get("boneName", "")),
                    anomaly_type=item.get("anomalyType", "jerk_spike"),
                    severity=item.get("severity", "warning"),
                    metric_value=float(item.get("metricValue", 0.0)),
                    threshold=float(item.get("threshold", 0.0)),
                    description=str(item.get("description", "")),
                    recommendation=str(item.get("recommendation", "")),
                )
            )
    return anomalies


def _parse_bone_summaries(raw_list: list[Any]) -> list[BoneMotionSummary]:
    summaries: list[BoneMotionSummary] = []
    for item in raw_list:
        if isinstance(item, dict):
            summaries.append(
                BoneMotionSummary(
                    bone_name=str(item.get("boneName", "")),
                    peak_velocity=float(item.get("peakVelocity", 0.0)),
                    peak_acceleration=float(item.get("peakAcceleration", 0.0)),
                    peak_jerk=float(item.get("peakJerk", 0.0)),
                    average_jerk=float(item.get("averageJerk", 0.0)),
                    smoothness_score=float(item.get("smoothnessScore", 1.0)),
                )
            )
    return summaries


def _parse_discontinuity_items(raw_list: list[Any]) -> list[CurveDiscontinuityItem]:
    items: list[CurveDiscontinuityItem] = []
    for item in raw_list:
        if isinstance(item, dict):
            items.append(
                CurveDiscontinuityItem(
                    curve_path=str(item.get("curvePath", "")),
                    property_name=str(item.get("propertyName", "")),
                    timestamp=float(item.get("timestamp", 0.0)),
                    issue_type=item.get("issueType", "quaternion_flip"),
                    severity=item.get("severity", "critical"),
                    current_value=float(item.get("currentValue", 0.0)),
                    description=str(item.get("description", "")),
                    suggested_fix=str(item.get("suggestedFix", "")),
                )
            )
    return items


@mcp.tool()
async def analyze_joint_motion(  # noqa: PLR0913
    clip_path: str,
    target_object_path: str,
    bones: list[str] | None = None,
    sample_fps: int = 60,
    jerk_threshold: float = 120.0,
    angular_jerk_threshold: float = 4000.0,
) -> JointMotionAnalysisResult:
    """
    Computes numerical velocity, acceleration, and jerk derivatives across animation curves.

    Detects sudden acceleration spikes (jerk), violent rotational snaps, and velocity reversals
    to identify jitter, snapping knees, and unnatural motion defects across time.

    Args:
        clip_path: Asset path to the AnimationClip to evaluate.
        target_object_path: Hierarchy path to the target GameObject in the scene.
        bones: Optional list of bone names or paths to evaluate (defaults to all key limbs/head).
        sample_fps: Sampling rate for discrete derivative calculation (default: 60 fps).
        jerk_threshold: Maximum allowable linear jerk in m/s^3 (default: 120.0).
        angular_jerk_threshold: Maximum allowable angular jerk in deg/s^3 (default: 4000.0).

    Returns:
        A JointMotionAnalysisResult with smoothness scores, detected anomalies, and recommendations.
    """
    if not await _bridge_supports(_CAPABILITY_MOTION_QA):
        return JointMotionAnalysisResult(
            success=False,
            error=f"Unity bridge does not support capability '{_CAPABILITY_MOTION_QA}'. Update Visora Unity package.",
            clip_path=clip_path,
            target_object_path=target_object_path,
        )

    try:
        resp = await animation_pkg.bridge.analyze_joint_motion_native(
            clip_path=clip_path,
            target_path=target_object_path,
            bones=bones,
            sample_fps=sample_fps,
            jerk_threshold=jerk_threshold,
            angular_jerk_threshold=angular_jerk_threshold,
        )

        if not resp.get("success", False):
            return JointMotionAnalysisResult(
                success=False,
                error=str(resp.get("error", "Failed to analyze joint motion")),
                clip_path=clip_path,
                target_object_path=target_object_path,
                warnings=[str(w) for w in resp.get("warnings", [])],
            )

        anomalies = _parse_anomalies(resp.get("anomalies", []))
        summaries = _parse_bone_summaries(resp.get("perBoneSummary", []))

        return JointMotionAnalysisResult(
            success=True,
            clip_path=clip_path,
            target_object_path=target_object_path,
            clip_duration=float(resp.get("clipDuration", 0.0)),
            sample_count=int(resp.get("sampleCount", 0)),
            sample_fps=float(resp.get("sampleFps", float(sample_fps))),
            overall_smoothness_score=float(resp.get("overallSmoothnessScore", 1.0)),
            anomalies=anomalies,
            per_bone_summary=summaries,
            recommendations=[str(r) for r in resp.get("recommendations", [])],
            warnings=[str(w) for w in resp.get("warnings", [])],
        )
    except Exception as exc:
        logger.exception("Error executing analyze_joint_motion")
        return JointMotionAnalysisResult(
            success=False,
            error=f"Bridge call failed: {exc}",
            clip_path=clip_path,
            target_object_path=target_object_path,
        )


@mcp.tool()
async def detect_curve_discontinuities(
    clip_path: str,
    filter_curves: list[str] | None = None,
    auto_fix: bool = False,
) -> CurveDiscontinuityResult:
    """
    Scans AnimationClip curves for quaternion sign flips, Euler jumps, and tangent singularities.

    Identifies antipodal quaternion flips (dot product < 0) that cause catastrophic 360° spins or
    camera snaps. With auto_fix=True, creates a pre-mutation backup and runs EnsureQuaternionContinuity.

    Args:
        clip_path: Asset path to the AnimationClip to scan.
        filter_curves: Optional list of bone names or curve paths to narrow the inspection.
        auto_fix: If True, writes a pre-mutation backup under VisoraBackups/ and repairs flips.

    Returns:
        A CurveDiscontinuityResult with detected issues and backup metadata if repaired.
    """
    if auto_fix:
        edit_mode_err = await _require_edit_mode()
        if edit_mode_err:
            return CurveDiscontinuityResult(
                success=False,
                error=edit_mode_err,
                clip_path=clip_path,
            )

    if not await _bridge_supports(_CAPABILITY_CURVE_DISCONTINUITY):
        return CurveDiscontinuityResult(
            success=False,
            error=f"Unity bridge does not support capability '{_CAPABILITY_CURVE_DISCONTINUITY}'. Update Visora Unity package.",
            clip_path=clip_path,
        )

    try:
        resp = await animation_pkg.bridge.detect_curve_discontinuities_native(
            clip_path=clip_path,
            filter_curves=filter_curves,
            auto_fix=auto_fix,
        )

        if not resp.get("success", False):
            return CurveDiscontinuityResult(
                success=False,
                error=str(resp.get("error", "Failed to detect curve discontinuities")),
                clip_path=clip_path,
                warnings=[str(w) for w in resp.get("warnings", [])],
            )

        items = _parse_discontinuity_items(resp.get("items", []))

        return CurveDiscontinuityResult(
            success=True,
            clip_path=clip_path,
            discontinuities_count=int(resp.get("discontinuitiesCount", len(items))),
            items=items,
            fix_applied=bool(resp.get("fixApplied", False)),
            backup_id=resp.get("backupId"),
            warnings=[str(w) for w in resp.get("warnings", [])],
        )
    except Exception as exc:
        logger.exception("Error executing detect_curve_discontinuities")
        return CurveDiscontinuityResult(
            success=False,
            error=f"Bridge call failed: {exc}",
            clip_path=clip_path,
        )


@mcp.tool()
async def compare_animation_previews(  # noqa: PLR0913
    baseline_preview_id: str,
    comparison_preview_id: str,
    baseline_slide_distance: float = 0.0,
    comparison_slide_distance: float = 0.0,
    baseline_peak_jerk: float = 0.0,
    comparison_peak_jerk: float = 0.0,
    baseline_peak_speed: float = 0.0,
    comparison_peak_speed: float = 0.0,
    baseline_camera_distance: float = 0.0,
    comparison_camera_distance: float = 0.0,
    keyframes_diff_count: int = 0,
) -> AnimationComparisonResult:
    """
    Compares two animation preview runs or diagnostic records to quantify improvement and detect regressions.

    Evaluates differential motion metrics (sliding reduction percentage, jerk reduction percentage,
    peak velocity deltas, camera framing stability) to confirm changes objectively before finalizing.

    Args:
        baseline_preview_id: Identifier of the baseline / before preview.
        comparison_preview_id: Identifier of the comparison / after preview.
        baseline_slide_distance: Total contact sliding distance (meters) before edits.
        comparison_slide_distance: Total contact sliding distance (meters) after edits.
        baseline_peak_jerk: Maximum jerk (m/s^3) before edits.
        comparison_peak_jerk: Maximum jerk (m/s^3) after edits.
        baseline_peak_speed: Peak speed (m/s) before edits.
        comparison_peak_speed: Peak speed (m/s) after edits.
        baseline_camera_distance: Distance to camera lens (m) before edits.
        comparison_camera_distance: Distance to camera lens (m) after edits.
        keyframes_diff_count: Number of keyframes altered between versions.

    Returns:
        An AnimationComparisonResult summarizing percentage improvements and regression warnings.
    """
    slide_reduction = 0.0
    if baseline_slide_distance > 0.0001:
        slide_reduction = ((baseline_slide_distance - comparison_slide_distance) / baseline_slide_distance) * 100.0

    jerk_reduction = 0.0
    if baseline_peak_jerk > 0.0001:
        jerk_reduction = ((baseline_peak_jerk - comparison_peak_jerk) / baseline_peak_jerk) * 100.0

    speed_delta = comparison_peak_speed - baseline_peak_speed
    cam_delta = comparison_camera_distance - baseline_camera_distance

    warnings: list[str] = []
    if comparison_slide_distance > baseline_slide_distance + 0.01:
        warnings.append(
            f"Regression: Foot sliding increased by {comparison_slide_distance - baseline_slide_distance:.2f}m."
        )
    if comparison_peak_jerk > baseline_peak_jerk * 1.2 and comparison_peak_jerk > 120.0:
        warnings.append(
            f"Regression: Peak jerk increased by {comparison_peak_jerk - baseline_peak_jerk:.1f} m/s^3 (more jittery)."
        )

    summary_parts = []
    if slide_reduction > 0:
        summary_parts.append(f"Foot sliding reduced by {slide_reduction:.1f}%")
    elif slide_reduction < 0:
        summary_parts.append(f"Foot sliding increased by {abs(slide_reduction):.1f}%")

    if jerk_reduction > 0:
        summary_parts.append(f"motion smoothness improved by {jerk_reduction:.1f}%")
    elif jerk_reduction < 0:
        summary_parts.append(f"peak jerk worsened by {abs(jerk_reduction):.1f}%")

    if not summary_parts:
        summary = "No significant metric divergence observed between preview runs."
    else:
        summary = "; ".join(summary_parts) + "."

    return AnimationComparisonResult(
        success=True,
        baseline_preview_id=baseline_preview_id,
        comparison_preview_id=comparison_preview_id,
        summary=summary,
        sliding_reduced_percent=round(slide_reduction, 2),
        jerk_reduced_percent=round(jerk_reduction, 2),
        peak_speed_delta=round(speed_delta, 3),
        framing_distance_delta=round(cam_delta, 3),
        keyframes_diff_count=keyframes_diff_count,
        regression_warnings=warnings,
    )


__all__ = [
    "analyze_joint_motion",
    "compare_animation_previews",
    "detect_curve_discontinuities",
]
