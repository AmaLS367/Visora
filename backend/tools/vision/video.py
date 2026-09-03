import base64
import time
from dataclasses import dataclass, field
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

# A frame that fails on a transient bridge condition is retried rather than ending the sequence: a
# domain reload drops a single frame, and losing the whole recording to it wastes the entire capture.
_FRAME_RETRY_ATTEMPTS = 3

# How many frames to discard while the Game View still shows pre-Play-Mode content. Kept small
# because a genuinely static scene looks identical too, and that is not an error.
_STALE_FRAME_ATTEMPTS = 2

# Below this changed-pixel ratio two frames are treated as showing the same thing.
_STATIC_FRAME_RATIO = 0.001

# Frame timing is measured, never assumed. Each source says how the timestamps were produced.
_TIMING_PYTHON_WALLCLOCK = "python_wallclock"


@dataclass
class _CaptureOutcome:
    """Result of the shared capture core, before either public tool shapes it into its own schema."""

    sequences: list[VideoFrameSequence] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def success(self) -> bool:
        return any(sequence.frames for sequence in self.sequences)


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


async def _capture_frame_with_retry(  # noqa: PLR0913
    frame_index: int,
    timestamp_seconds: float,
    camera_name: str,
    subject_path: str | None,
    mode: str,
    width: int,
    height: int,
    sequence_warnings: list[str],
) -> VideoFrame | None:
    """
    Captures one frame, retrying transient bridge failures instead of abandoning the sequence.

    Returns None once the attempts are exhausted, leaving the caller to stop with a partial sequence.
    """
    last_error: Exception | None = None

    for attempt in range(_FRAME_RETRY_ATTEMPTS):
        try:
            return await _capture_video_frame(
                frame_index=frame_index,
                timestamp_seconds=timestamp_seconds,
                camera_name=camera_name,
                subject_path=subject_path,
                mode=mode,
                width=width,
                height=height,
            )
        except Exception as exc:
            last_error = exc
            vision_pkg.logger.info(
                "Video frame %s capture attempt %s/%s failed: %s",
                frame_index,
                attempt + 1,
                _FRAME_RETRY_ATTEMPTS,
                exc,
            )
            if attempt < _FRAME_RETRY_ATTEMPTS - 1:
                await vision_pkg._sleep(0.2)

    vision_pkg.logger.exception("Video frame capture failed", exc_info=last_error)
    sequence_warnings.append(f"frame {frame_index} capture failed after {_FRAME_RETRY_ATTEMPTS} attempts: {last_error}")
    return None


async def _discard_stale_frames(  # noqa: PLR0913
    baseline: VideoFrame | None,
    camera_name: str,
    subject_path: str | None,
    mode: str,
    width: int,
    height: int,
    warnings: list[str],
) -> None:
    """
    Drops frames that still show pre-Play-Mode content.

    Entering Play Mode does not guarantee the Game View has rendered the running scene by the time
    the bridge answers, so the first frame can be a stale image of Edit Mode. Comparing against a
    frame captured before the transition identifies that; a static scene looks the same too, which is
    why this gives up quickly and warns rather than failing.
    """
    if baseline is None:
        return

    for _ in range(_STALE_FRAME_ATTEMPTS):
        try:
            candidate = await _capture_video_frame(
                frame_index=-1,
                timestamp_seconds=0.0,
                camera_name=camera_name,
                subject_path=subject_path,
                mode=mode,
                width=width,
                height=height,
            )
        except Exception as exc:
            vision_pkg.logger.info("Warm-up frame capture failed, continuing with capture: %s", exc)
            return

        metric = _motion_metric_from_frames(
            from_frame=-1,
            to_frame=0,
            before_base64=baseline.image_base64,
            after_base64=candidate.image_base64,
        )
        if metric.changed_pixel_ratio >= _STATIC_FRAME_RATIO:
            return

        await vision_pkg._sleep(0.1)

    warnings.append(
        "Game View still matched its pre-Play-Mode content after warm-up; the first frames may be "
        "stale, or the scene may simply be static."
    )


async def _capture_baseline_frame(
    camera_name: str,
    subject_path: str | None,
    mode: str,
    width: int,
    height: int,
) -> VideoFrame | None:
    """Captures the reference frame used to recognise a stale first Game View frame. Never raises."""
    try:
        return await _capture_video_frame(
            frame_index=-1,
            timestamp_seconds=0.0,
            camera_name=camera_name,
            subject_path=subject_path,
            mode=mode,
            width=width,
            height=height,
        )
    except Exception as exc:
        vision_pkg.logger.info("Baseline frame for stale-frame detection unavailable: %s", exc)
        return None


async def _capture_sequence(  # noqa: PLR0913
    camera_name: str,
    subject_path: str | None,
    mode: str,
    duration_seconds: float,
    fps: int,
    width: int,
    height: int,
    count: int,
    include_motion_metrics: bool,
    sequence_warnings: list[str],
) -> VideoFrameSequence:
    """Records one camera's frames, measuring the timing actually achieved rather than assuming it."""
    frames: list[VideoFrame] = []
    started_at = time.perf_counter()

    for frame_index in range(count):
        frame = await _capture_frame_with_retry(
            frame_index=frame_index,
            timestamp_seconds=time.perf_counter() - started_at,
            camera_name=camera_name,
            subject_path=subject_path,
            mode=mode,
            width=width,
            height=height,
            sequence_warnings=sequence_warnings,
        )
        if frame is None:
            break

        frames.append(frame)
        sequence_warnings.extend(f"frame {frame_index}: {warning}" for warning in frame.warnings)

        if frame_index < count - 1:
            await vision_pkg._sleep(1 / fps)

    actual_fps: float | None = None
    if len(frames) >= 2:
        elapsed = frames[-1].timestamp_seconds - frames[0].timestamp_seconds
        if elapsed > 0:
            actual_fps = (len(frames) - 1) / elapsed
            if actual_fps < fps * 0.9:
                sequence_warnings.append(
                    f"Frames were sampled at {actual_fps:.1f} fps instead of the requested {fps} fps; "
                    "each frame costs a bridge round trip, so timestamps reflect the real capture times."
                )

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
        if motion_metrics and max(metric.changed_pixel_ratio for metric in motion_metrics) < _STATIC_FRAME_RATIO:
            sequence_warnings.append("near-zero visual motion detected across sampled frames")

    return VideoFrameSequence(
        camera_name=camera_name,
        mode=mode,
        duration_seconds=duration_seconds,
        fps=fps,
        actual_fps=actual_fps,
        timing_source=_TIMING_PYTHON_WALLCLOCK,
        frames=frames,
        motion_metrics=motion_metrics,
        warnings=sequence_warnings,
    )


async def _enter_play_mode_for_capture(  # noqa: PLR0913
    *,
    camera_name: str,
    subject_path: str | None,
    mode: str,
    width: int,
    height: int,
    warnings: list[str],
) -> None:
    """
    Enters Play Mode and waits until the view is showing the running scene.

    Only game_camera can show a stale frame: it reads whatever the Game View last rendered, which
    right after a domain reload may still be the Edit Mode image. diagnostic_lit builds and renders
    its own camera per frame, so it cannot return pre-Play-Mode content and pays no warm-up cost.
    """
    baseline = (
        await _capture_baseline_frame(
            camera_name=camera_name,
            subject_path=subject_path,
            mode=mode,
            width=width,
            height=height,
        )
        if mode == "game_camera"
        else None
    )

    try:
        await vision_pkg.bridge.set_play_mode(True)
    except Exception as exc:
        # Unity drops the connection as it unloads the domain; the wait below is what confirms
        # the transition actually happened.
        vision_pkg.logger.info("Play mode transition initiated, awaiting domain reload: %s", exc)

    await vision_pkg.bridge.wait_for_play_mode(True, timeout_seconds=30.0)

    await _discard_stale_frames(
        baseline=baseline,
        camera_name=camera_name,
        subject_path=subject_path,
        mode=mode,
        width=width,
        height=height,
        warnings=warnings,
    )


async def _restore_edit_mode(warnings: list[str]) -> None:
    """Returns the editor to Edit Mode, reporting failure as a warning rather than losing the capture."""
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
        warnings.append(f"failed to restore play mode: {exc}")


async def _capture_frame_sequences(  # noqa: PLR0913
    *,
    camera_names: list[str],
    subject_path: str | None,
    mode: str,
    duration_seconds: float,
    fps: int,
    width: int,
    height: int,
    enter_play_mode: bool,
    include_motion_metrics: bool,
    max_fps: int,
) -> _CaptureOutcome:
    """
    Shared capture core owning validation, Play Mode lifecycle, and frame timing.

    Both public video tools run through here with their own fps ceiling. get_video_frames caps fps
    because it returns every frame as base64 in the payload; MP4 export has no such payload cost and
    so allows a higher rate. Routing one tool through the other reapplied the wrong ceiling and made
    get_video_mp4 fail on its own default fps.
    """
    validation_error = _validate_video_request(duration_seconds, fps, width, height, max_fps=max_fps)
    if validation_error is not None:
        return _CaptureOutcome(error=validation_error)

    if mode not in {"diagnostic_lit", "game_camera"}:
        return _CaptureOutcome(error="mode must be either diagnostic_lit or game_camera")

    count = _frame_count(duration_seconds, fps)
    outcome = _CaptureOutcome()
    started_play_mode = False

    try:
        state = await vision_pkg.bridge.get_editor_state()
        was_playing = bool(state.get("isPlaying", False))

        if enter_play_mode and not was_playing:
            await _enter_play_mode_for_capture(
                camera_name=camera_names[0],
                subject_path=subject_path,
                mode=mode,
                width=width,
                height=height,
                warnings=outcome.warnings,
            )
            started_play_mode = True

        for camera_name in camera_names:
            outcome.sequences.append(
                await _capture_sequence(
                    camera_name=camera_name,
                    subject_path=subject_path,
                    mode=mode,
                    duration_seconds=duration_seconds,
                    fps=fps,
                    width=width,
                    height=height,
                    count=count,
                    include_motion_metrics=include_motion_metrics,
                    sequence_warnings=[],
                )
            )

        if not outcome.success:
            outcome.error = "no video frames were captured"
        return outcome
    except Exception as exc:
        vision_pkg.logger.exception("Video frame sequence capture failed")
        outcome.error = str(exc)
        return outcome
    finally:
        if started_play_mode:
            await _restore_edit_mode(outcome.warnings)


@mcp.tool()
async def get_video_frames(  # noqa: PLR0913
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
        fps: Sampling frame rate (1 to 12). Every frame is returned as base64 in the payload, which is
            what bounds this rate; use get_video_mp4 for higher frame rates. Defaults to 6.
        width: Frame width in pixels. Defaults to 1280.
        height: Frame height in pixels. Defaults to 720.
        enter_play_mode: If True, temporarily enters Play Mode during capture. Visora polls the bridge
            to ensure domain reload completes before frames are captured. For authored clips, consider
            sample_animation_clip in Edit Mode as a lightweight alternative.
        include_motion_metrics: If True, computes delta motion metrics between adjacent frames.

    Returns:
        A VideoFramesResult containing captured frame sequences, motion metrics, and interpretation guidance.
    """
    outcome = await _capture_frame_sequences(
        camera_names=camera_names or ["Main Camera"],
        subject_path=subject_path,
        mode=mode,
        duration_seconds=duration_seconds,
        fps=fps,
        width=width,
        height=height,
        enter_play_mode=enter_play_mode,
        include_motion_metrics=include_motion_metrics,
        max_fps=12,
    )

    if not outcome.sequences and outcome.error is not None:
        return VideoFramesResult(
            success=False,
            error=outcome.error,
            warnings=outcome.warnings,
            recommended_interpretation="No frames were captured because the request could not start.",
        )

    return VideoFramesResult(
        success=outcome.success,
        error=outcome.error,
        sequences=outcome.sequences,
        warnings=[
            "Use sampled frames and motion_metrics for temporal reasoning when the model cannot inspect MP4 directly.",
            *outcome.warnings,
        ],
        recommended_interpretation=(
            "Use diagnostic_lit frames for model and animation motion. Use motion_metrics to find changed intervals; "
            "use MP4 only when the consuming model can inspect video directly. Frame timestamps are measured, so "
            "compare them against the requested fps before reading the sequence as real-time motion."
        ),
    )


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
        The MP4 is encoded at the frame rate actually achieved, so playback runs at real speed.
    """
    outcome = await _capture_frame_sequences(
        camera_names=[camera_name],
        subject_path=subject_path,
        mode=mode,
        duration_seconds=duration_seconds,
        fps=fps,
        width=width,
        height=height,
        enter_play_mode=enter_play_mode,
        include_motion_metrics=False,
        max_fps=30,
    )

    if not outcome.success or not outcome.sequences or not outcome.sequences[0].frames:
        return VideoMp4Result(
            success=False,
            error=outcome.error or "no frames available for MP4 export",
            camera_name=camera_name,
            mode=mode,
            duration_seconds=duration_seconds,
            fps=fps,
            width=width,
            height=height,
            warnings=outcome.warnings,
        )

    sequence = outcome.sequences[0]
    warnings = [*outcome.warnings, *sequence.warnings]
    encode_fps = sequence.actual_fps or float(fps)

    try:
        video_bytes, artifact_path = vision_pkg._encode_frames_to_mp4(
            [frame.image_base64 for frame in sequence.frames], encode_fps, width, height
        )
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
            warnings=warnings,
        )

    return VideoMp4Result(
        success=True,
        video_base64=base64.b64encode(video_bytes).decode("ascii"),
        artifact_path=str(artifact_path),
        camera_name=camera_name,
        mode=mode,
        duration_seconds=duration_seconds,
        fps=fps,
        actual_fps=sequence.actual_fps,
        timing_source=sequence.timing_source,
        width=width,
        height=height,
        warnings=warnings,
    )


__all__ = [
    "_capture_frame_sequences",
    "_capture_video_frame",
    "get_video_frames",
    "get_video_mp4",
]
