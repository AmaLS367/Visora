import base64
import time
from dataclasses import dataclass, field
from itertools import pairwise
from typing import Any

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
_TIMING_NATIVE_REALTIME = "native_realtime"
_TIMING_EDIT_MODE_SAMPLED = "edit_mode_sampled"

# Play Mode records whatever the running game does; authored_clip instead samples a clip at exact
# timestamps in Edit Mode, which is deterministic at any frame rate and needs no domain reload.
_AUTHORED_CLIP_MODE = "authored_clip"
_PLAY_MODE_CAPTURE_MODES = {"diagnostic_lit", "game_camera"}

# Unity records a whole sequence itself when the package advertises these. Recording per frame over
# HTTP costs a round trip each time, which caps the real rate far below any requested one.
_NATIVE_SEQUENCE_FEATURE = {
    "game_camera": "camera_sequence_realtime",
    "diagnostic_lit": "camera_diagnostic_sequence",
}


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
    frame_warnings: dict[str, list[int]] = {}
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
        for warning in frame.warnings:
            frame_warnings.setdefault(warning, []).append(frame_index)

        if frame_index < count - 1:
            await vision_pkg._sleep(1 / fps)

    for warning, indices in frame_warnings.items():
        if len(indices) == 1:
            sequence_warnings.append(f"frame {indices[0]}: {warning}")
        else:
            sequence_warnings.append(f"{warning} (reported on {len(indices)} frames)")

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


async def _bridge_supports(feature: str) -> bool:
    """
    Reports whether the bridge advertises a capability, treating any failure as "no".

    A missing capability is a routing decision, not an error: the caller simply records frame by
    frame instead, so an unreachable or older bridge must not turn into a failed capture here.
    """
    try:
        return bool(await vision_pkg.bridge.supports_feature(feature))
    except Exception as exc:
        vision_pkg.logger.info("Bridge capability '%s' could not be confirmed: %s", feature, exc)
        return False


def _sequence_from_native_payload(  # noqa: PLR0913
    payload: dict[str, Any],
    camera_name: str,
    mode: str,
    duration_seconds: float,
    fps: int,
    width: int,
    height: int,
    include_motion_metrics: bool,
) -> VideoFrameSequence | None:
    """Converts a Unity-recorded sequence into the tool schema, or None if Unity reported failure."""
    if not payload.get("success"):
        return None

    raw_frames = payload.get("frames")
    if not isinstance(raw_frames, list) or not raw_frames:
        return None

    resolved_camera = str(payload.get("cameraName") or camera_name)
    frames: list[VideoFrame] = []
    for position, raw_frame in enumerate(raw_frames):
        if not isinstance(raw_frame, dict):
            continue
        image_base64 = raw_frame.get("imageBase64")
        if not isinstance(image_base64, str) or not image_base64:
            continue
        frames.append(
            VideoFrame(
                frame_index=int(raw_frame.get("frameIndex", position)),
                timestamp_seconds=float(raw_frame.get("timestamp", 0.0)),
                camera_name=resolved_camera,
                mode=mode,
                image_base64=image_base64,
                width=int(payload.get("width", width) or width),
                height=int(payload.get("height", height) or height),
            )
        )

    if not frames:
        return None

    raw_warnings = payload.get("warnings")
    warnings = [str(item) for item in raw_warnings] if isinstance(raw_warnings, list) else []

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
            warnings.append("near-zero visual motion detected across sampled frames")

    actual_fps = payload.get("actualFps")

    return VideoFrameSequence(
        camera_name=resolved_camera,
        mode=mode,
        duration_seconds=duration_seconds,
        fps=fps,
        actual_fps=float(actual_fps) if isinstance(actual_fps, (int, float)) and actual_fps > 0 else None,
        timing_source=str(payload.get("timingSource") or _TIMING_NATIVE_REALTIME),
        frames=frames,
        motion_metrics=motion_metrics,
        warnings=warnings,
    )


async def _capture_native_sequence(  # noqa: PLR0913
    camera_name: str,
    subject_path: str | None,
    mode: str,
    duration_seconds: float,
    fps: int,
    width: int,
    height: int,
    count: int,
    include_motion_metrics: bool,
) -> VideoFrameSequence | None:
    """
    Asks Unity to record the whole sequence and return it in one response.

    Unity advances the frames on its own clock, so this is the only path where a requested frame rate
    can actually be met - recording over HTTP spends a round trip per frame. Returns None when the
    recording could not be produced, leaving the caller to fall back to per-frame capture.
    """
    interval = 1.0 / fps
    try:
        if mode == "game_camera":
            payload = await vision_pkg.bridge.capture_sequence_native(
                camera_name=camera_name,
                width=width,
                height=height,
                frame_count=count,
                interval=interval,
            )
        else:
            payload = await vision_pkg.bridge.capture_diagnostic_sequence_native(
                subject_path=subject_path,
                width=width,
                height=height,
                frame_count=count,
                interval=interval,
            )
    except Exception as exc:
        vision_pkg.logger.warning("Native sequence capture failed, falling back to per-frame capture: %s", exc)
        return None

    sequence = _sequence_from_native_payload(
        payload=payload,
        camera_name=camera_name,
        mode=mode,
        duration_seconds=duration_seconds,
        fps=fps,
        width=width,
        height=height,
        include_motion_metrics=include_motion_metrics,
    )
    if sequence is None:
        vision_pkg.logger.warning(
            "Native sequence capture returned no usable frames (%s), falling back to per-frame capture",
            payload.get("error"),
        )
    return sequence


async def _capture_authored_clip(  # noqa: PLR0913
    *,
    camera_name: str,
    clip_path: str | None,
    target_object_path: str | None,
    duration_seconds: float,
    fps: int,
    width: int,
    height: int,
    count: int,
    include_motion_metrics: bool,
) -> _CaptureOutcome:
    """
    Renders an authored clip by sampling it at exact timestamps in Edit Mode.

    Unlike Play Mode recording this hits the requested frame rate exactly, because Unity poses the
    rig per frame instead of racing a running game. It shows only what the clip drives - no physics,
    particles, or gameplay logic - and it needs the native package, since there is no way to sample a
    clip frame by frame over the legacy bridge without re-posing the rig on every request.
    """
    if not clip_path or not target_object_path:
        return _CaptureOutcome(error=f"mode '{_AUTHORED_CLIP_MODE}' requires both clip_path and target_object_path")

    if not await _bridge_supports("animation_preview_sequence"):
        return _CaptureOutcome(
            error=(
                f"mode '{_AUTHORED_CLIP_MODE}' requires the Visora Unity package with the "
                "animation_preview_sequence capability; install or update it, or use game_camera."
            )
        )

    try:
        payload = await vision_pkg.bridge.preview_animation_sequence_native(
            camera_name=camera_name,
            clip_path=clip_path,
            target_object_path=target_object_path,
            width=width,
            height=height,
            frame_count=count,
            fps=float(fps),
        )
    except Exception as exc:
        vision_pkg.logger.exception("Authored clip preview failed")
        return _CaptureOutcome(error=str(exc))

    sequence = _sequence_from_native_payload(
        payload=payload,
        camera_name=camera_name,
        mode=_AUTHORED_CLIP_MODE,
        duration_seconds=duration_seconds,
        fps=fps,
        width=width,
        height=height,
        include_motion_metrics=include_motion_metrics,
    )
    if sequence is None:
        return _CaptureOutcome(error=str(payload.get("error") or "authored clip preview produced no frames"))

    outcome = _CaptureOutcome(sequences=[sequence])
    if not payload.get("poseRestored", False):
        outcome.warnings.append("Unity did not confirm the target pose was restored after sampling.")
    if payload.get("sceneDirtiedByPreview", False):
        outcome.warnings.append(
            "Sampling marked the scene as modified even though the pose was restored; discard the "
            "change rather than saving the scene."
        )
    return outcome


async def _enter_play_mode_for_capture(  # noqa: PLR0913
    *,
    camera_name: str,
    subject_path: str | None,
    mode: str,
    width: int,
    height: int,
    warnings: list[str],
    needs_warm_up: bool,
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
        if needs_warm_up and mode == "game_camera"
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
    clip_path: str | None = None,
    target_object_path: str | None = None,
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

    if mode not in _PLAY_MODE_CAPTURE_MODES and mode != _AUTHORED_CLIP_MODE:
        return _CaptureOutcome(error="mode must be diagnostic_lit, game_camera, or authored_clip")

    count = _frame_count(duration_seconds, fps)

    if mode == _AUTHORED_CLIP_MODE:
        return await _capture_authored_clip(
            camera_name=camera_names[0],
            clip_path=clip_path,
            target_object_path=target_object_path,
            duration_seconds=duration_seconds,
            fps=fps,
            width=width,
            height=height,
            count=count,
            include_motion_metrics=include_motion_metrics,
        )
    outcome = _CaptureOutcome()
    started_play_mode = False

    try:
        state = await vision_pkg.bridge.get_editor_state()
        was_playing = bool(state.get("isPlaying", False))

        use_native = await _bridge_supports(_NATIVE_SEQUENCE_FEATURE[mode])

        if enter_play_mode and not was_playing:
            # Ownership is claimed before the attempt, not after it. Unity accepts the transition and
            # then drops the connection for the domain reload, so a failure while waiting still
            # leaves the editor playing; restoring Edit Mode we never actually left is harmless,
            # stranding the editor in Play Mode is not.
            started_play_mode = True
            await _enter_play_mode_for_capture(
                camera_name=camera_names[0],
                subject_path=subject_path,
                mode=mode,
                width=width,
                height=height,
                warnings=outcome.warnings,
                needs_warm_up=not use_native,
            )

        for camera_name in camera_names:
            sequence = (
                await _capture_native_sequence(
                    camera_name=camera_name,
                    subject_path=subject_path,
                    mode=mode,
                    duration_seconds=duration_seconds,
                    fps=fps,
                    width=width,
                    height=height,
                    count=count,
                    include_motion_metrics=include_motion_metrics,
                )
                if use_native
                else None
            )

            if sequence is None:
                if use_native:
                    outcome.warnings.append(
                        "Native sequence recording was unavailable; frames were captured one bridge "
                        "round trip at a time, so the real frame rate is far below the requested one."
                    )
                sequence = await _capture_sequence(
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

            outcome.sequences.append(sequence)

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
    clip_path: str | None = None,
    target_object_path: str | None = None,
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
        mode: Capture mode. "diagnostic_lit" renders a neutral temporary rig, "game_camera" records a
            scene camera in Play Mode, and "authored_clip" samples an AnimationClip at exact
            timestamps in Edit Mode - deterministic at any fps, but showing only what the clip drives.
        clip_path: AnimationClip asset path or name. Required for mode "authored_clip".
        target_object_path: Scene path of the GameObject the clip is applied to. Required for
            mode "authored_clip".
        duration_seconds: Capture duration in seconds (0.1 to 10.0). Defaults to 2.0.
        fps: Sampling frame rate (1 to 12). Every frame is returned as base64 in the payload, which is
            what bounds this rate; use get_video_mp4 for higher frame rates. Defaults to 6.
        width: Frame width in pixels. Defaults to 1280.
        height: Frame height in pixels. Defaults to 720.
        enter_play_mode: If True, temporarily enters Play Mode during capture. Visora polls the bridge
            to ensure domain reload completes before frames are captured. Ignored by "authored_clip",
            which samples in Edit Mode and needs no domain reload.
        include_motion_metrics: If True, computes delta motion metrics between adjacent frames.

    Returns:
        A VideoFramesResult containing captured frame sequences, motion metrics, and interpretation guidance.
    """
    outcome = await _capture_frame_sequences(
        camera_names=camera_names or ["Main Camera"],
        subject_path=subject_path,
        mode=mode,
        clip_path=clip_path,
        target_object_path=target_object_path,
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
    clip_path: str | None = None,
    target_object_path: str | None = None,
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
        mode: Capture mode. "diagnostic_lit" renders a neutral temporary rig, "game_camera" records a
            scene camera in Play Mode, and "authored_clip" samples an AnimationClip at exact
            timestamps in Edit Mode - the only mode that hits a high fps exactly.
        clip_path: AnimationClip asset path or name. Required for mode "authored_clip".
        target_object_path: Scene path of the GameObject the clip is applied to. Required for
            mode "authored_clip".
        duration_seconds: Capture duration in seconds (0.1 to 10.0). Defaults to 2.0.
        fps: Recording frame rate (1 to 30). Defaults to 24.
        width: Video width in pixels. Defaults to 1280.
        height: Video height in pixels. Defaults to 720.
        enter_play_mode: If True, temporarily enters Play Mode during capture. Visora polls the bridge
            to ensure domain reload completes before frames are captured. Ignored by "authored_clip",
            which samples in Edit Mode and needs no domain reload.

    Returns:
        A VideoMp4Result containing base64-encoded MP4 bytes, saved artifact path, and video metadata.
        The MP4 is encoded at the frame rate actually achieved, so playback runs at real speed.
    """
    outcome = await _capture_frame_sequences(
        camera_names=[camera_name],
        subject_path=subject_path,
        mode=mode,
        clip_path=clip_path,
        target_object_path=target_object_path,
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
