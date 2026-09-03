import base64
from itertools import pairwise

import backend.tools.vision as vision_pkg
from backend.app import mcp
from backend.schemas import (
    FrameMotionMetrics,
    VideoFrame,
    VideoFrameSequence,
    VideoFramesResult,
    VideoMp4Result,
)
from backend.tools.vision.image_utils import (
    _encode_frames_to_mp4,
    _extract_result_payload,
    _frame_count,
    _motion_metric_from_frames,
    _payload_warnings,
    _validate_video_request,
)
from backend.tools.vision.scripts import (
    _camera_screenshot_code,
    _diagnostic_scene_capture_code,
)


async def _capture_video_frame(  # noqa: PLR0913
    frame_index: int,
    timestamp_seconds: float,
    camera_name: str,
    subject_path: str | None,
    mode: str,
    width: int,
    height: int,
) -> VideoFrame:
    if mode == "diagnostic_lit":
        response = await vision_pkg.bridge.execute_capability(
            _diagnostic_scene_capture_code(subject_path, width, height)
        )
        fallback_camera_name = "Visora Diagnostic Camera"
    elif mode == "game_camera":
        response = await vision_pkg.bridge.render_camera(
            _camera_screenshot_code(camera_name, width, height), camera_name, width, height
        )
        fallback_camera_name = camera_name
    else:
        raise ValueError("mode must be either diagnostic_lit or game_camera")

    payload = _extract_result_payload(response)
    image_base64 = payload.get("imageBase64") or payload.get("image_base64")
    if not isinstance(image_base64, str) or not image_base64:
        raise RuntimeError("Unity video frame response did not include imageBase64")

    return VideoFrame(
        frame_index=frame_index,
        timestamp_seconds=timestamp_seconds,
        camera_name=str(payload.get("cameraName", fallback_camera_name)),
        mode=mode,
        image_base64=image_base64,
        width=int(payload.get("width", width)),
        height=int(payload.get("height", height)),
        warnings=_payload_warnings(payload),
    )


@mcp.tool()
async def get_video_frames(  # noqa: PLR0912, PLR0913, PLR0915
    camera_names: list[str] | None = None,
    subject_path: str | None = None,
    mode: str = "diagnostic_lit",
    duration_seconds: float = 2.0,
    fps: int = 6,
    width: int = 1280,
    height: int = 720,
    enter_play_mode: bool = True,
    include_motion_metrics: bool = True,
) -> VideoFramesResult:
    """
    Captures sampled camera frames for agents that reason over frame sequences instead of raw video.

    Args:
        camera_names: Optional list of Unity camera names to sample from. Defaults to ["Main Camera"].
        subject_path: Optional hierarchy path to the subject GameObject to frame.
        mode: Capture mode ("diagnostic_lit" or "game_camera"). Defaults to "diagnostic_lit".
        duration_seconds: Capture duration in seconds (0.1 to 10.0). Defaults to 2.0.
        fps: Sampling frame rate (1 to 12). Defaults to 6.
        width: Frame width in pixels. Defaults to 1280.
        height: Frame height in pixels. Defaults to 720.
        enter_play_mode: If True, temporarily enters Play Mode during capture. Visora polls the bridge
            to ensure domain reload completes before frames are captured. For authored clips, consider
            sample_animation_clip in Edit Mode as a lightweight alternative.
        include_motion_metrics: If True, computes delta motion metrics between adjacent frames.

    Returns:
        A VideoFramesResult containing captured frame sequences, motion metrics, and interpretation guidance.
    """
    validation_error = _validate_video_request(duration_seconds, fps, width, height, max_fps=12)
    if validation_error is not None:
        return VideoFramesResult(
            success=False,
            error=validation_error,
            recommended_interpretation="No frames were captured because the request exceeded v1 validation limits.",
        )
    if mode not in {"diagnostic_lit", "game_camera"}:
        return VideoFramesResult(
            success=False,
            error="mode must be either diagnostic_lit or game_camera",
            recommended_interpretation="Use diagnostic_lit for model motion inspection or game_camera for authored camera checks.",
        )

    camera_names = camera_names or ["Main Camera"]
    count = _frame_count(duration_seconds, fps)
    warnings: list[str] = [
        "Use sampled frames and motion_metrics for temporal reasoning when the model cannot inspect MP4 directly.",
    ]
    sequences: list[VideoFrameSequence] = []
    started_play_mode = False

    try:
        state = await vision_pkg.bridge.get_editor_state()
        was_playing = bool(state.get("isPlaying", False))
        if enter_play_mode and not was_playing:
            try:
                await vision_pkg.bridge.set_play_mode(True)
            except Exception as exc:
                vision_pkg.logger.info("Play mode transition initiated, awaiting domain reload: %s", exc)
            started_play_mode = True
            await vision_pkg.bridge.wait_for_play_mode(True, timeout_seconds=30.0)

        for camera_name in camera_names:
            frames: list[VideoFrame] = []
            sequence_warnings: list[str] = []
            for frame_index in range(count):
                timestamp_seconds = frame_index / fps
                try:
                    frame = await _capture_video_frame(
                        frame_index=frame_index,
                        timestamp_seconds=timestamp_seconds,
                        camera_name=camera_name,
                        subject_path=subject_path,
                        mode=mode,
                        width=width,
                        height=height,
                    )
                    frames.append(frame)
                    sequence_warnings.extend(f"frame {frame_index}: {warning}" for warning in frame.warnings)
                except Exception as exc:
                    vision_pkg.logger.exception("Video frame capture failed")
                    sequence_warnings.append(f"frame {frame_index} capture failed: {exc}")
                    break

                if frame_index < count - 1:
                    await vision_pkg._sleep(1 / fps)

            motion_metrics: list[FrameMotionMetrics] = []
            if include_motion_metrics:
                motion_metrics = [
                    _motion_metric_from_frames(
                        from_frame=previous.frame_index,
                        to_frame=current.frame_index,
                        before_base64=previous.image_base64,
                        after_base64=current.image_base64,
                    )
                    for previous, current in pairwise(frames)
                ]
                if motion_metrics and max(metric.changed_pixel_ratio for metric in motion_metrics) < 0.001:
                    sequence_warnings.append("near-zero visual motion detected across sampled frames")

            sequences.append(
                VideoFrameSequence(
                    camera_name=camera_name,
                    mode=mode,
                    duration_seconds=duration_seconds,
                    fps=fps,
                    frames=frames,
                    motion_metrics=motion_metrics,
                    warnings=sequence_warnings,
                ),
            )

        success = any(sequence.frames for sequence in sequences)
        result = VideoFramesResult(
            success=success,
            error=None if success else "no video frames were captured",
            sequences=sequences,
            warnings=warnings,
            recommended_interpretation=(
                "Use diagnostic_lit frames for model and animation motion. Use motion_metrics to find changed intervals; "
                "use MP4 only when the consuming model can inspect video directly."
            ),
        )
        return result
    except Exception as exc:
        vision_pkg.logger.exception("Video frame sequence capture failed")
        result = VideoFramesResult(
            success=False,
            error=str(exc),
            sequences=sequences,
            warnings=warnings,
            recommended_interpretation="Video frame capture failed before Visora could produce a reliable sequence.",
        )
        return result
    finally:
        if started_play_mode:
            try:
                try:
                    await vision_pkg.bridge.wait_for_editor_ready(timeout_seconds=15.0)
                except Exception as exc:
                    vision_pkg.logger.debug("Editor state check before exit play mode: %s", exc)

                try:
                    await vision_pkg.bridge.set_play_mode(False)
                except Exception as exc:
                    vision_pkg.logger.info("Exit play mode requested, awaiting domain reload: %s", exc)

                await vision_pkg.bridge.wait_for_play_mode(False, timeout_seconds=30.0)
            except Exception as exc:
                vision_pkg.logger.exception("Failed to restore Play Mode after video capture")
                restore_warning = f"failed to restore play mode: {exc}"
                warnings.append(restore_warning)
                if "result" in locals():
                    result.warnings.append(restore_warning)


@mcp.tool()
async def get_video_mp4(  # noqa: PLR0913
    camera_name: str = "Main Camera",
    subject_path: str | None = None,
    mode: str = "diagnostic_lit",
    duration_seconds: float = 2.0,
    fps: int = 24,
    width: int = 1280,
    height: int = 720,
    enter_play_mode: bool = True,
) -> VideoMp4Result:
    """
    Captures a short camera video and returns MP4 bytes for video-capable models.

    Args:
        camera_name: Name of the Unity camera used for video recording. Defaults to "Main Camera".
        subject_path: Optional hierarchy path to the subject GameObject to frame.
        mode: Capture mode ("diagnostic_lit" or "game_camera"). Defaults to "diagnostic_lit".
        duration_seconds: Capture duration in seconds (0.1 to 10.0). Defaults to 2.0.
        fps: Recording frame rate (1 to 30). Defaults to 24.
        width: Video width in pixels. Defaults to 1280.
        height: Video height in pixels. Defaults to 720.
        enter_play_mode: If True, temporarily enters Play Mode during capture. Visora polls the bridge
            to ensure domain reload completes before frames are captured. For authored clips, consider
            sample_animation_clip in Edit Mode as a lightweight alternative.

    Returns:
        A VideoMp4Result containing base64-encoded MP4 bytes, saved artifact path, and video metadata.
    """
    validation_error = _validate_video_request(duration_seconds, fps, width, height, max_fps=30)
    if validation_error is not None:
        return VideoMp4Result(
            success=False,
            error=validation_error,
            camera_name=camera_name,
            mode=mode,
            duration_seconds=duration_seconds,
            fps=fps,
            width=width,
            height=height,
        )

    frames_result = await vision_pkg.get_video_frames(
        camera_names=[camera_name],
        subject_path=subject_path,
        mode=mode,
        duration_seconds=duration_seconds,
        fps=fps,
        width=width,
        height=height,
        enter_play_mode=enter_play_mode,
        include_motion_metrics=False,
    )
    if not frames_result.success or not frames_result.sequences or not frames_result.sequences[0].frames:
        return VideoMp4Result(
            success=False,
            error=frames_result.error or "no frames available for MP4 export",
            camera_name=camera_name,
            mode=mode,
            duration_seconds=duration_seconds,
            fps=fps,
            width=width,
            height=height,
            warnings=frames_result.warnings,
        )

    frame_images = [frame.image_base64 for frame in frames_result.sequences[0].frames]
    try:
        video_bytes, artifact_path = vision_pkg._encode_frames_to_mp4(frame_images, fps, width, height)
    except Exception as exc:
        vision_pkg.logger.exception("MP4 export failed")
        return VideoMp4Result(
            success=False,
            error=str(exc),
            camera_name=camera_name,
            mode=mode,
            duration_seconds=duration_seconds,
            fps=fps,
            width=width,
            height=height,
            warnings=frames_result.warnings,
        )

    return VideoMp4Result(
        success=True,
        video_base64=base64.b64encode(video_bytes).decode("ascii"),
        artifact_path=str(artifact_path),
        camera_name=camera_name,
        mode=mode,
        duration_seconds=duration_seconds,
        fps=fps,
        width=width,
        height=height,
        warnings=frames_result.warnings,
    )


__all__ = [
    "_capture_video_frame",
    "get_video_frames",
    "get_video_mp4",
]
