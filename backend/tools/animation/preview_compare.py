import logging
from pathlib import Path

from PIL import Image as PILImage

from backend.schemas.preview_record import (
    AnimationPreviewComparisonResult,
    AnimationPreviewInputsDiff,
    AnimationPreviewMotionDiff,
    AnimationPreviewRecord,
)
from backend.tools.vision.image_utils import (
    _create_side_by_side_comparison,
    _load_image,
    _save_image_artifact,
)

logger = logging.getLogger(__name__)


def _compare_action_markers(
    baseline: AnimationPreviewRecord,
    comparison: AnimationPreviewRecord,
) -> list[str]:
    events_diff: list[str] = []
    base_markers = {m.label: m.time for m in baseline.action_markers}
    comp_markers = {m.label: m.time for m in comparison.action_markers}

    for label, comp_time in comp_markers.items():
        if label not in base_markers:
            events_diff.append(f"Added marker '{label}' at t={comp_time:.2f}s")
        else:
            base_time = base_markers[label]
            shift = comp_time - base_time
            if abs(shift) > 0.01:
                events_diff.append(
                    f"Shifted marker '{label}' by {shift:+.2f}s (t={base_time:.2f}s -> {comp_time:.2f}s)"
                )

    for label, base_time in base_markers.items():
        if label not in comp_markers:
            events_diff.append(f"Removed marker '{label}' at t={base_time:.2f}s")

    return events_diff


def _create_comparison_image(
    baseline: AnimationPreviewRecord,
    comparison: AnimationPreviewRecord,
) -> Path | None:
    """Creates a side-by-side comparison artifact of both previews' contact sheets, if available."""
    base_sheet = baseline.artifacts.contact_sheet_path
    comp_sheet = comparison.artifacts.contact_sheet_path

    if not base_sheet or not comp_sheet:
        return None

    path_base = Path(base_sheet)
    path_comp = Path(comp_sheet)

    if not path_base.is_file() or not path_comp.is_file():
        return None

    try:
        img_base = _load_image(path_base)
        img_comp = _load_image(path_comp)
        stitched = _create_side_by_side_comparison(
            img_base,
            img_comp,
            left_label=f"Baseline ({baseline.preview_id})",
            right_label=f"Comparison ({comparison.preview_id})",
        )
        saved_path = _save_image_artifact(
            stitched,
            prefix=f"diff_{baseline.preview_id}_{comparison.preview_id}",
            subfolder="animation_previews/comparisons",
        )
        return saved_path
    except Exception as exc:
        logger.warning("Failed to generate preview comparison image: %s", exc)
        return None


def compare_records(  # noqa: PLR0912, PLR0913, PLR0915
    baseline: AnimationPreviewRecord,
    comparison: AnimationPreviewRecord,
    baseline_slide_distance: float = 0.0,
    comparison_slide_distance: float = 0.0,
    baseline_peak_jerk: float = 0.0,
    comparison_peak_jerk: float = 0.0,
    baseline_peak_speed: float = 0.0,
    comparison_peak_speed: float = 0.0,
    baseline_camera_distance: float = 0.0,
    comparison_camera_distance: float = 0.0,
    keyframes_diff_count: int = 0,
) -> tuple[AnimationPreviewComparisonResult, Path | None]:
    """
    Compares two AnimationPreviewRecords across inputs, temporal motion, markers, and visual contact sheets.
    """
    # 1. Inputs diff
    clip_changed = baseline.clip.clip_path != comparison.clip.clip_path
    length_delta = round(comparison.clip.length - baseline.clip.length, 3)
    camera_changed = baseline.camera.rendered_camera_name != comparison.camera.rendered_camera_name
    base_fps = baseline.capture_settings.actual_fps or baseline.capture_settings.effective_fps
    comp_fps = comparison.capture_settings.actual_fps or comparison.capture_settings.effective_fps
    fps_delta = round(comp_fps - base_fps, 2)
    res_changed = (
        baseline.capture_settings.width != comparison.capture_settings.width
        or baseline.capture_settings.height != comparison.capture_settings.height
    )

    inputs_diff = AnimationPreviewInputsDiff(
        clip_path_changed=clip_changed,
        baseline_clip_path=baseline.clip.clip_path,
        comparison_clip_path=comparison.clip.clip_path,
        clip_length_delta=length_delta,
        camera_changed=camera_changed,
        baseline_camera=baseline.camera.rendered_camera_name,
        comparison_camera=comparison.camera.rendered_camera_name,
        fps_delta=fps_delta,
        resolution_changed=res_changed,
    )

    # 2. Motion diff
    base_motion = baseline.motion_summary
    comp_motion = comparison.motion_summary
    peak_timestamp_delta: float | None = None
    if (
        base_motion
        and comp_motion
        and base_motion.peak_motion_timestamp is not None
        and comp_motion.peak_motion_timestamp is not None
    ):
        peak_timestamp_delta = round(comp_motion.peak_motion_timestamp - base_motion.peak_motion_timestamp, 3)

    peak_ratio_delta = round(
        (comp_motion.peak_changed_pixel_ratio if comp_motion else 0.0)
        - (base_motion.peak_changed_pixel_ratio if base_motion else 0.0),
        3,
    )
    mean_ratio_delta = round(
        (comp_motion.mean_changed_pixel_ratio if comp_motion else 0.0)
        - (base_motion.mean_changed_pixel_ratio if base_motion else 0.0),
        3,
    )
    was_static = base_motion.is_static if base_motion else False
    is_now_static = comp_motion.is_static if comp_motion else False
    static_changed = was_static != is_now_static

    motion_diff = AnimationPreviewMotionDiff(
        peak_motion_timestamp_delta=peak_timestamp_delta,
        peak_changed_pixel_ratio_delta=peak_ratio_delta,
        mean_changed_pixel_ratio_delta=mean_ratio_delta,
        static_status_changed=static_changed,
        is_now_static=is_now_static,
        was_static=was_static,
    )

    # 3. Action markers diff
    events_diff = _compare_action_markers(baseline, comparison)

    # 4. QA explicit float metric diffs
    slide_reduction = 0.0
    if baseline_slide_distance > 0.0001:
        slide_reduction = ((baseline_slide_distance - comparison_slide_distance) / baseline_slide_distance) * 100.0

    jerk_reduction = 0.0
    if baseline_peak_jerk > 0.0001:
        jerk_reduction = ((baseline_peak_jerk - comparison_peak_jerk) / baseline_peak_jerk) * 100.0

    speed_delta = comparison_peak_speed - baseline_peak_speed
    cam_delta = comparison_camera_distance - baseline_camera_distance

    # 5. Classify improvements & regressions
    improvements: list[str] = []
    regressions: list[str] = []

    if is_now_static and not was_static:
        regressions.append("Regression: Visual motion ceased completely; clip evaluated as static.")
    elif was_static and not is_now_static:
        improvements.append("Improvement: Visual motion restored; clip is no longer static.")

    if slide_reduction > 0.01:
        improvements.append(f"Foot sliding reduced by {slide_reduction:.1f}%.")
    elif comparison_slide_distance > baseline_slide_distance + 0.01:
        regressions.append(
            f"Regression: Foot sliding increased by {comparison_slide_distance - baseline_slide_distance:.2f}m."
        )

    if jerk_reduction > 0.01:
        improvements.append(f"Motion smoothness improved by {jerk_reduction:.1f}%.")
    elif comparison_peak_jerk > baseline_peak_jerk * 1.2 and comparison_peak_jerk > 120.0:
        regressions.append(
            f"Regression: Peak jerk increased by {comparison_peak_jerk - baseline_peak_jerk:.1f} m/s^3 (more jittery)."
        )

    if baseline.camera.framing_status_before == "visible" and comparison.camera.framing_status_before in (
        "clipped",
        "off_screen",
        "behind_camera",
    ):
        regressions.append(f"Regression: Camera framing degraded to '{comparison.camera.framing_status_before}'.")

    if not comparison.editor_state.pose_restored and baseline.editor_state.pose_restored:
        regressions.append("Regression: Unity target pose was not restored after preview.")

    # 6. Side-by-side contact sheet artifact
    diff_image_path = _create_comparison_image(baseline, comparison)

    # 7. Summary
    summary_parts: list[str] = []
    if improvements:
        summary_parts.extend(improvements)
    if regressions:
        summary_parts.extend(regressions)
    if peak_timestamp_delta is not None and abs(peak_timestamp_delta) > 0.01:
        summary_parts.append(f"Peak motion shifted by {peak_timestamp_delta:+.2f}s.")
    if not summary_parts:
        summary_parts.append("No significant divergence observed between preview runs.")

    summary = " ".join(summary_parts)

    result = AnimationPreviewComparisonResult(
        success=True,
        baseline_preview_id=baseline.preview_id,
        comparison_preview_id=comparison.preview_id,
        summary=summary,
        inputs_diff=inputs_diff,
        motion_diff=motion_diff,
        visual_comparison_sheet_path=str(diff_image_path) if diff_image_path else None,
        events_diff=events_diff,
        sliding_reduced_percent=round(slide_reduction, 2),
        jerk_reduced_percent=round(jerk_reduction, 2),
        peak_speed_delta=round(speed_delta, 3),
        framing_distance_delta=round(cam_delta, 3),
        keyframes_diff_count=keyframes_diff_count,
        improvements=improvements,
        regression_warnings=regressions,
    )
    return result, diff_image_path
