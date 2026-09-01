import asyncio
import base64
import logging
from itertools import pairwise
from typing import cast

from backend.app import mcp
from backend.bridge import UnityBridge
from backend.schemas import (
    CameraFramingDiagnosticsResult,
    FrameMotionMetrics,
    ProjectWorldPointsResult,
    SceneCameraInfo,
    ScreenPoint,
    ScreenshotResult,
    VideoFrame,
    VideoFrameSequence,
    VideoFramesResult,
    VideoMp4Result,
    VisualCapture,
    VisualComparisonResult,
    VisualInspectionResult,
)
from backend.tools.vision.image_utils import (
    _capture_from_payload,
    _decode_image,
    _encode_frames_to_mp4,
    _extract_result_payload,
    _frame_count,
    _motion_metric_from_frames,
    _normalize_threshold,
    _payload_float,
    _payload_warnings,
    _validate_video_request,
    compare_images_data,
)
from backend.tools.vision.scripts import (
    _camera_framing_diagnostics_code,
    _camera_screenshot_code,
    _diagnostic_scene_capture_code,
    _hierarchy_path_code,
    _list_scene_cameras_code,
    _project_world_points_code,
)

logger = logging.getLogger("backend.tools.vision")
bridge = UnityBridge()


async def _sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)


@mcp.tool()
async def list_scene_cameras() -> list[SceneCameraInfo]:
    """
    Lists active Unity scene cameras so agents can choose a real camera before rendering or projection.

    Returns:
        A compact list of scene camera metadata.
    """
    response = await bridge.execute_code(_list_scene_cameras_code())
    payload = _extract_result_payload(response)
    cameras = payload.get("cameras", [])
    if not isinstance(cameras, list):
        raise RuntimeError("Unity camera inventory response did not include cameras")

    return [
        SceneCameraInfo(
            name=str(camera.get("name", "")),
            path=str(camera.get("path", "")),
            enabled=bool(camera.get("enabled", False)),
            active=bool(camera.get("active", False)),
            tag=str(camera.get("tag", "")),
            depth=_payload_float(camera.get("depth")),
            field_of_view=_payload_float(camera.get("fieldOfView", camera.get("field_of_view"))),
            orthographic=bool(camera.get("orthographic", False)),
            orthographic_size=_payload_float(camera.get("orthographicSize", camera.get("orthographic_size"))),
        )
        for camera in cameras
        if isinstance(camera, dict)
    ]


@mcp.tool()
async def screenshot(
    camera_name: str = "Main Camera",
    width: int = 1920,
    height: int = 1080,
) -> ScreenshotResult:
    """
    Captures a high-resolution screenshot from the specified editor or gameplay camera.

    Args:
        camera_name: Name of the Unity camera in the active scene to render from.
        width: Desired width of the screenshot in pixels.
        height: Desired height of the screenshot in pixels.

    Returns:
        A ScreenshotResult object containing base64-encoded image data or error details.
    """
    if width <= 0 or height <= 0:
        return ScreenshotResult(success=False, error="width and height must be positive integers")

    try:
        response = await bridge.execute_code(_camera_screenshot_code(camera_name, width, height))
        payload = _extract_result_payload(response)
        image_base64 = payload.get("imageBase64") or payload.get("image_base64")
        if not isinstance(image_base64, str) or not image_base64:
            return ScreenshotResult(success=False, error="Unity screenshot response did not include imageBase64")

        return ScreenshotResult(
            success=True,
            image_base64=image_base64,
            width=int(payload.get("width", width)),
            height=int(payload.get("height", height)),
            camera_name=str(payload.get("cameraName", camera_name)),
            warnings=_payload_warnings(payload),
        )
    except Exception as exc:
        logger.exception("Screenshot capture failed")
        return ScreenshotResult(success=False, error=str(exc))


@mcp.tool()
def compare_screenshots(
    before_image_base64: str,
    after_image_base64: str,
    threshold: int = 8,
) -> VisualComparisonResult:
    """
    Compares two screenshots and returns compact visual-change diagnostics.

    Args:
        before_image_base64: Base64 encoded PNG/JPEG image before a scene change.
        after_image_base64: Base64 encoded PNG/JPEG image after a scene change.
        threshold: Per-channel delta threshold required to count a pixel as changed.

    Returns:
        A VisualComparisonResult with changed-pixel metrics and changed bounds.
    """
    return compare_images_data(before_image_base64, after_image_base64, threshold)


@mcp.tool()
async def inspect_scene_visual(
    subject_path: str | None = None,
    camera_name: str = "Main Camera",
    width: int = 1280,
    height: int = 720,
) -> VisualInspectionResult:
    """
    Captures a scene with both authored camera rendering and diagnostic inspection rendering.

    Use this when the user asks what is visible in a Unity scene, whether a model/pose/animation looks correct,
    or when production lighting, environment, or final camera framing may be incomplete. Agents should inspect
    diagnostic_lit for model and animation visibility before drawing conclusions from game_camera darkness.
    """
    if width <= 0 or height <= 0:
        return VisualInspectionResult(
            success=False,
            error="width and height must be positive integers",
            subject_path=subject_path,
            recommended_interpretation="No captures were produced because the requested dimensions were invalid.",
        )

    captures: list[VisualCapture] = []
    warnings: list[str] = [
        "Use diagnostic_lit for model, pose, rig, and animation inspection when authored lighting is incomplete.",
        "Use game_camera for final player-facing composition only; darkness there is not proof that the subject is missing.",
    ]

    try:
        game_response = await bridge.execute_code(_camera_screenshot_code(camera_name, width, height))
        game_payload = _extract_result_payload(game_response)
        captures.append(_capture_from_payload("game_camera", game_payload, camera_name))
        warnings.extend(f"game_camera: {warning}" for warning in _payload_warnings(game_payload))
    except Exception as exc:
        logger.warning("Game camera visual inspection capture failed: %s", exc)
        warnings.append(f"game camera capture failed: {exc}")

    try:
        diagnostic_response = await bridge.execute_code(_diagnostic_scene_capture_code(subject_path, width, height))
        diagnostic_payload = _extract_result_payload(diagnostic_response)
        captures.append(_capture_from_payload("diagnostic_lit", diagnostic_payload, "Visora Diagnostic Camera"))
        warnings.extend(f"diagnostic_lit: {warning}" for warning in _payload_warnings(diagnostic_payload))
    except Exception as exc:
        logger.exception("Diagnostic visual inspection capture failed")
        warnings.append(f"diagnostic capture failed: {exc}")

    if not captures:
        return VisualInspectionResult(
            success=False,
            error="all visual inspection captures failed",
            subject_path=subject_path,
            captures=[],
            warnings=warnings,
            recommended_interpretation=(
                "No visual capture was available. Check Unity bridge status, scene renderers, and camera names before "
                "making visual conclusions."
            ),
        )

    return VisualInspectionResult(
        success=True,
        subject_path=subject_path,
        captures=captures,
        warnings=warnings,
        recommended_interpretation=(
            "Use diagnostic_lit first to inspect the actual model, pose, animation, mesh, and silhouette. "
            "Do not conclude the scene is empty, broken, or missing from a dark game_camera capture alone. "
            "Use game_camera only for authored lighting, final composition, and player-facing framing checks."
        ),
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
        response = await bridge.execute_code(_diagnostic_scene_capture_code(subject_path, width, height))
        fallback_camera_name = "Visora Diagnostic Camera"
    elif mode == "game_camera":
        response = await bridge.execute_code(_camera_screenshot_code(camera_name, width, height))
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
        state = await bridge.get_editor_state()
        was_playing = bool(state.get("isPlaying", False))
        if enter_play_mode and not was_playing:
            await bridge.set_play_mode(True)
            started_play_mode = True
            await _sleep(5.0)

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
                    logger.exception("Video frame capture failed")
                    sequence_warnings.append(f"frame {frame_index} capture failed: {exc}")
                    break

                if frame_index < count - 1:
                    await _sleep(1 / fps)

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
        logger.exception("Video frame sequence capture failed")
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
                await bridge.set_play_mode(False)
            except Exception as exc:
                logger.exception("Failed to restore Play Mode after video capture")
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

    frames_result = await get_video_frames(
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
        video_bytes, artifact_path = _encode_frames_to_mp4(frame_images, fps, width, height)
    except Exception as exc:
        logger.exception("MP4 export failed")
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


@mcp.tool()
async def project_world_points(
    points: list[list[float]],
    camera_name: str = "Main Camera",
) -> ProjectWorldPointsResult:
    """
    Projects 3D world coordinates onto the 2D screen coordinate viewport of a camera.

    Args:
        points: A list of 3D world points, where each point is a list of [x, y, z] floats.
        camera_name: Name of the Unity camera used to compute projections.

    Returns:
        A ProjectWorldPointsResult with a list of 2D screen positions.
    """
    if any(len(point) != 3 for point in points):
        return ProjectWorldPointsResult(
            success=False,
            error="each world point must contain exactly 3 coordinates",
        )

    try:
        response = await bridge.execute_code(_project_world_points_code(points, camera_name))
        payload = _extract_result_payload(response)
        raw_points = payload.get("screenPoints", payload.get("screen_points", []))
        if not isinstance(raw_points, list):
            return ProjectWorldPointsResult(
                success=False, error="Unity projection response did not include screenPoints"
            )

        return ProjectWorldPointsResult(
            success=True,
            screen_points=[
                ScreenPoint(
                    x=float(point.get("x", 0.0)),
                    y=float(point.get("y", 0.0)),
                    z=float(point.get("z", 0.0)),
                    is_behind_camera=bool(point.get("isBehindCamera", point.get("is_behind_camera", False))),
                )
                for point in raw_points
                if isinstance(point, dict)
            ],
        )
    except Exception as exc:
        logger.exception("World point projection failed")
        return ProjectWorldPointsResult(success=False, error=str(exc))


@mcp.tool()
async def diagnose_camera_framing(
    subject_path: str,
    camera_name: str = "Main Camera",
) -> CameraFramingDiagnosticsResult:
    """
    Diagnoses whether a subject renderer bounds are visible and well framed by a Unity camera.

    Args:
        subject_path: Hierarchy path or GameObject name for the inspected subject.
        camera_name: Name of the Unity camera used for viewport projection.

    Returns:
        A CameraFramingDiagnosticsResult with viewport bounds and framing status.
    """
    try:
        response = await bridge.execute_code(_camera_framing_diagnostics_code(subject_path, camera_name))
        payload = _extract_result_payload(response)
        viewport_bounds = payload.get("viewportBounds", payload.get("viewport_bounds"))
        return CameraFramingDiagnosticsResult(
            success=True,
            subject_path=str(payload.get("subjectPath", subject_path)),
            camera_name=str(payload.get("cameraName", camera_name)),
            viewport_bounds=[float(value) for value in viewport_bounds] if isinstance(viewport_bounds, list) else None,
            visible_ratio=float(payload.get("visibleRatio", payload.get("visible_ratio", 0.0))),
            is_visible=bool(payload.get("isVisible", payload.get("is_visible", False))),
            is_behind_camera=bool(payload.get("isBehindCamera", payload.get("is_behind_camera", False))),
            is_clipped=bool(payload.get("isClipped", payload.get("is_clipped", False))),
            framing_status=str(payload.get("framingStatus", payload.get("framing_status", "unknown"))),
            warnings=_payload_warnings(payload),
        )
    except Exception as exc:
        logger.exception("Camera framing diagnostics failed")
        return CameraFramingDiagnosticsResult(
            success=False,
            error=str(exc),
            subject_path=subject_path,
            camera_name=camera_name,
            is_visible=False,
            warnings=[],
        )


__all__ = [
    "_camera_framing_diagnostics_code",
    "_camera_screenshot_code",
    "_capture_from_payload",
    "_capture_video_frame",
    "_decode_image",
    "_diagnostic_scene_capture_code",
    "_encode_frames_to_mp4",
    "_extract_result_payload",
    "_frame_count",
    "_hierarchy_path_code",
    "_list_scene_cameras_code",
    "_motion_metric_from_frames",
    "_normalize_threshold",
    "_payload_float",
    "_payload_warnings",
    "_project_world_points_code",
    "_sleep",
    "_validate_video_request",
    "bridge",
    "compare_screenshots",
    "diagnose_camera_framing",
    "get_video_frames",
    "get_video_mp4",
    "inspect_scene_visual",
    "list_scene_cameras",
    "project_world_points",
    "screenshot",
]
