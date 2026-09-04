import base64
from typing import Any

import backend.tools.animation as animation_pkg
import backend.tools.vision as vision_pkg
from backend.app import mcp
from backend.schemas import (
    AnimationPreviewKeyFrame,
    AnimationPreviewMotionSummary,
    AnimationPreviewResult,
)
from backend.tools.animation.inspector import inspect_animation_clip
from backend.tools.animation.preview_keyframes import select_key_frames
from backend.tools.animation.preview_math import (
    build_motion_timeline,
    measure_actual_fps,
    resolve_frame_budget,
    summarize_motion,
)

# The established bridge contract uses endTime=0 as "to the clip end". Preserve that external
# behavior for older get_video_* callers while still representing preview_animation's explicit
# zero-length range as its one frame at time zero.
_EMPTY_RANGE_NATIVE_END = 0.000001


async def _bridge_supports(feature: str) -> bool:
    """Treat a missing or unreachable capability as unavailable instead of hiding the reason."""
    try:
        return bool(await animation_pkg.bridge.supports_feature(feature))
    except Exception as exc:
        animation_pkg.logger.info("Bridge capability '%s' could not be confirmed: %s", feature, exc)
        return False


def _payload_warnings(payload: dict[str, Any]) -> list[str]:
    raw_warnings = payload.get("warnings", [])
    if isinstance(raw_warnings, list):
        return [str(warning) for warning in raw_warnings]
    return [str(raw_warnings)] if raw_warnings else []


def _failed_preview(  # noqa: PLR0913
    *,
    error: str,
    target_object_path: str,
    clip_path: str,
    camera_name: str,
    start_time: float,
    end_time: float,
    fps: int,
    width: int,
    height: int,
) -> AnimationPreviewResult:
    return AnimationPreviewResult(
        success=False,
        error=error,
        clip_path=clip_path,
        target_object_path=target_object_path,
        camera_name=camera_name,
        rendered_camera_name=camera_name,
        start_time=start_time,
        end_time=end_time,
        fps=fps,
        width=width,
        height=height,
        recommended_interpretation="Resolve the reported error before relying on this animation preview.",
    )


@mcp.tool()
async def preview_animation(  # noqa: PLR0911, PLR0912, PLR0913, PLR0915
    target_object_path: str,
    clip_path: str,
    camera_name: str = "Main Camera",
    start_time: float = 0.0,
    end_time: float | None = None,
    fps: int = 24,
    width: int = 640,
    height: int = 360,
    auto_frame: bool = True,
    max_key_frames: int = 6,
    include_video_base64: bool = False,
    include_clip_diagnostics: bool = True,
) -> AnimationPreviewResult:
    """Capture and summarize an authored AnimationClip in one Edit Mode-only review call."""
    requested_end = end_time if end_time is not None else start_time
    if fps < 1:
        return _failed_preview(
            error="fps must be at least 1",
            target_object_path=target_object_path,
            clip_path=clip_path,
            camera_name=camera_name,
            start_time=start_time,
            end_time=requested_end,
            fps=fps,
            width=width,
            height=height,
        )
    if width <= 0 or height <= 0:
        return _failed_preview(
            error="width and height must be positive integers",
            target_object_path=target_object_path,
            clip_path=clip_path,
            camera_name=camera_name,
            start_time=start_time,
            end_time=requested_end,
            fps=fps,
            width=width,
            height=height,
        )
    if width > 1920 or height > 1080:
        return _failed_preview(
            error="width and height must not exceed 1920x1080",
            target_object_path=target_object_path,
            clip_path=clip_path,
            camera_name=camera_name,
            start_time=start_time,
            end_time=requested_end,
            fps=fps,
            width=width,
            height=height,
        )

    try:
        editor_state = await animation_pkg.bridge.get_editor_state()
    except Exception as exc:
        return _failed_preview(
            error=str(exc),
            target_object_path=target_object_path,
            clip_path=clip_path,
            camera_name=camera_name,
            start_time=start_time,
            end_time=requested_end,
            fps=fps,
            width=width,
            height=height,
        )
    if bool(editor_state.get("isPlaying", False)):
        return _failed_preview(
            error='preview_animation requires Edit Mode; use get_video_mp4(mode="game_camera") to record a running game.',
            target_object_path=target_object_path,
            clip_path=clip_path,
            camera_name=camera_name,
            start_time=start_time,
            end_time=requested_end,
            fps=fps,
            width=width,
            height=height,
        )

    clip = await inspect_animation_clip(clip_path)
    if not clip.success:
        return _failed_preview(
            error=clip.error or f"AnimationClip '{clip_path}' could not be inspected.",
            target_object_path=target_object_path,
            clip_path=clip_path,
            camera_name=camera_name,
            start_time=start_time,
            end_time=requested_end,
            fps=fps,
            width=width,
            height=height,
        )

    clip_length = max(0.0, float(clip.length or 0.0))
    range_start = min(max(start_time, 0.0), clip_length)
    range_end = clip_length if end_time is None else min(max(end_time, range_start), clip_length)
    budget = resolve_frame_budget(range_start, range_end, fps)

    supports_autoframe = await _bridge_supports("animation_preview_autoframe")
    use_auto_frame = auto_frame and supports_autoframe
    native_end_time = (
        _EMPTY_RANGE_NATIVE_END
        if budget.start_time == 0.0 and budget.end_time == 0.0 and clip_length > 0.0
        else budget.end_time
    )

    try:
        payload = await animation_pkg.bridge.preview_animation_sequence_native(
            camera_name=camera_name,
            clip_path=clip_path,
            target_object_path=target_object_path,
            width=width,
            height=height,
            frame_count=budget.frame_count,
            fps=budget.effective_fps,
            start_time=budget.start_time,
            end_time=native_end_time,
            auto_frame=use_auto_frame,
        )
    except Exception as exc:
        return _failed_preview(
            error=str(exc),
            target_object_path=target_object_path,
            clip_path=clip_path,
            camera_name=camera_name,
            start_time=budget.start_time,
            end_time=budget.end_time,
            fps=fps,
            width=width,
            height=height,
        )

    if not bool(payload.get("success", False)):
        return _failed_preview(
            error=str(payload.get("error") or "Animation preview produced no frames."),
            target_object_path=target_object_path,
            clip_path=clip_path,
            camera_name=camera_name,
            start_time=budget.start_time,
            end_time=budget.end_time,
            fps=fps,
            width=width,
            height=height,
        )

    raw_frames = payload.get("frames")
    frames = [frame for frame in raw_frames if isinstance(frame, dict)] if isinstance(raw_frames, list) else []
    images = [
        str(frame["imageBase64"])
        for frame in frames
        if isinstance(frame.get("imageBase64"), str) and frame["imageBase64"]
    ]
    timestamps = [
        float(frame.get("timestamp", 0.0))
        for frame in frames
        if isinstance(frame.get("imageBase64"), str) and frame["imageBase64"]
    ]
    if not images:
        return _failed_preview(
            error="Animation preview produced no usable frames.",
            target_object_path=target_object_path,
            clip_path=clip_path,
            camera_name=camera_name,
            start_time=budget.start_time,
            end_time=budget.end_time,
            fps=fps,
            width=width,
            height=height,
        )

    motion_timeline = build_motion_timeline(images)
    motion_summary = summarize_motion(motion_timeline, timestamps)
    events = [(event.time, event.function_name) for event in clip.events]
    choices = select_key_frames(timestamps, motion_timeline, events, max_key_frames)
    result_width = int(payload.get("width") or width)
    result_height = int(payload.get("height") or height)
    range_duration = budget.end_time - budget.start_time
    key_frames = [
        AnimationPreviewKeyFrame(
            frame_index=choice.frame_index,
            timestamp_seconds=timestamps[choice.frame_index],
            normalized_time=(timestamps[choice.frame_index] - budget.start_time) / range_duration
            if range_duration > 0
            else 0.0,
            source=choice.source,
            event_functions=choice.event_functions,
            image_base64=images[choice.frame_index],
            width=result_width,
            height=result_height,
            changed_pixel_ratio_from_previous=(
                motion_timeline[choice.frame_index - 1] if choice.frame_index > 0 else None
            ),
        )
        for choice in choices
    ]

    warnings = _payload_warnings(payload)
    auto_frame_status = "disabled" if not auto_frame else str(payload.get("autoFrameStatus") or "unsupported")
    if auto_frame and not supports_autoframe:
        auto_frame_status = "unsupported"
        warnings.append(
            "The bridge does not advertise animation_preview_autoframe; the requested camera was used unchanged."
        )
    if auto_frame_status == "failed":
        warnings.append("Auto-framing failed; the requested camera was used unchanged.")
    if budget.frame_ceiling_applied:
        warnings.append("Sampling rate was lowered to keep the preview within the frame capture ceiling.")
    if budget.range_truncated:
        warnings.append("Preview range was truncated because even 1 fps exceeded the frame capture ceiling.")
    if not bool(payload.get("poseRestored", False)):
        warnings.append("Unity did not confirm the target pose was restored after sampling.")
    if bool(payload.get("sceneDirtiedByPreview", False)):
        warnings.append("Sampling marked the scene as modified; discard the change rather than saving the scene.")
    unresolved_paths = int(payload.get("unresolvedCurvePaths") or 0)
    if unresolved_paths:
        warnings.append(f"{unresolved_paths} non-humanoid curve path(s) did not resolve under the target.")
    if motion_summary.is_static:
        warnings.append("Near-zero visual motion was detected across the sampled frames.")

    actual_fps = measure_actual_fps(timestamps)
    video_bytes: bytes | None = None
    video_artifact_path: str | None = None
    if len(images) < 2:
        warnings.append("A single captured frame does not produce an MP4 preview.")
    else:
        try:
            video_bytes, artifact_path = vision_pkg._encode_frames_to_mp4(
                images, actual_fps or budget.effective_fps, result_width, result_height
            )
            video_artifact_path = str(artifact_path)
        except Exception as exc:
            animation_pkg.logger.exception("Animation preview MP4 export failed")
            warnings.append(f"MP4 export failed: {exc}")

    preview_camera_created = bool(payload.get("previewCameraCreated", False))
    return AnimationPreviewResult(
        success=True,
        clip_name=clip.clip_name,
        clip_path=clip.clip_path or clip_path,
        clip_length=clip_length,
        loop_time=clip.loop_time or False,
        target_object_path=target_object_path,
        camera_name=camera_name,
        rendered_camera_name=str(payload.get("previewCameraUsed") or payload.get("cameraName") or camera_name),
        auto_frame_status=auto_frame_status,
        framing_status_before=(str(payload["framingStatusBefore"]) if payload.get("framingStatusBefore") else None),
        start_time=budget.start_time,
        end_time=budget.end_time,
        fps=fps,
        effective_fps=budget.effective_fps,
        actual_fps=actual_fps,
        frame_ceiling_applied=budget.frame_ceiling_applied,
        range_truncated=budget.range_truncated,
        timing_source=str(payload.get("timingSource") or "edit_mode_sampled"),
        frame_count=len(images),
        width=result_width,
        height=result_height,
        video_artifact_path=video_artifact_path,
        video_base64=base64.b64encode(video_bytes).decode("ascii") if include_video_base64 and video_bytes else None,
        key_frames=key_frames,
        motion_timeline=motion_timeline,
        motion_summary=AnimationPreviewMotionSummary(
            peak_motion_timestamp=motion_summary.peak_motion_timestamp,
            peak_changed_pixel_ratio=motion_summary.peak_changed_pixel_ratio,
            mean_changed_pixel_ratio=motion_summary.mean_changed_pixel_ratio,
            static_intervals=[[start, end] for start, end in motion_summary.static_intervals],
            is_static=motion_summary.is_static,
        ),
        dangerous_curves=[warning.description for warning in clip.dangerous_curves] if include_clip_diagnostics else [],
        pose_restored=bool(payload.get("poseRestored", False)),
        preview_camera_destroyed=bool(payload.get("previewCameraDestroyed", False)) if preview_camera_created else None,
        scene_dirtied_by_preview=bool(payload.get("sceneDirtiedByPreview", False)),
        warnings=warnings,
        recommended_interpretation=(
            "The sampled frames show near-zero visual motion; inspect clip curves and target bindings before treating the clip as static."
            if motion_summary.is_static
            else "Review key frames in timestamp order; motion peaks mark the frames with the greatest visual change."
        ),
    )


__all__ = ["preview_animation"]
