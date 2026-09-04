import math
from dataclasses import dataclass

# Mirrors CameraRenderingService.MaxSequenceFrames: every frame is held in memory as a base64 PNG
# until the whole sequence is serialized, so this bounds the response size, not the clip length.
MAX_SEQUENCE_FRAMES = 240

# Below this the preview stops being a preview, so the range is shortened instead of sampling slower.
MIN_PREVIEW_FPS = 1.0


@dataclass(frozen=True)
class FrameBudget:
    """How much of the clip is sampled, at what rate, and what had to give to stay in bounds."""

    start_time: float
    end_time: float
    frame_count: int
    effective_fps: float
    frame_ceiling_applied: bool
    range_truncated: bool


def _frames_for(duration: float, fps: float) -> int:
    return math.floor(duration * fps) + 1


def resolve_frame_budget(start_time: float, end_time: float, requested_fps: int) -> FrameBudget:
    """
    Fits the requested range and rate inside the frame ceiling, preferring a coarser rate to a shorter clip.

    Truncating the range would show an agent the first third of an animation while it believes it saw
    all of it, so the sampling rate gives way first. Only a range too long to cover at even
    MIN_PREVIEW_FPS is shortened, and that case is reported separately.
    """
    duration = end_time - start_time
    if duration <= 0:
        return FrameBudget(
            start_time=start_time,
            end_time=start_time,
            frame_count=1,
            effective_fps=float(requested_fps),
            frame_ceiling_applied=False,
            range_truncated=False,
        )

    ceiling_fps = (MAX_SEQUENCE_FRAMES - 1) / duration
    # Truncated, never rounded: rounding up could buy one frame more than the ceiling allows.
    effective_fps = math.floor(min(float(requested_fps), ceiling_fps) * 100) / 100
    frame_ceiling_applied = effective_fps < requested_fps

    if effective_fps >= MIN_PREVIEW_FPS:
        return FrameBudget(
            start_time=start_time,
            end_time=end_time,
            frame_count=_frames_for(duration, effective_fps),
            effective_fps=effective_fps,
            frame_ceiling_applied=frame_ceiling_applied,
            range_truncated=False,
        )

    covered = (MAX_SEQUENCE_FRAMES - 1) / MIN_PREVIEW_FPS
    return FrameBudget(
        start_time=start_time,
        end_time=start_time + covered,
        frame_count=MAX_SEQUENCE_FRAMES,
        effective_fps=MIN_PREVIEW_FPS,
        frame_ceiling_applied=True,
        range_truncated=True,
    )


def measure_actual_fps(timestamps: list[float]) -> float | None:
    """
    Derives the rate the frames actually exhibit, from their own timestamps.

    Unity clamps the final sample to the range end, so the last timestamp can fall short of the
    requested end_time; dividing by the requested range would overstate the rate.
    """
    if len(timestamps) < 2:
        return None
    elapsed = timestamps[-1] - timestamps[0]
    if elapsed <= 0:
        return None
    return (len(timestamps) - 1) / elapsed


__all__ = [
    "MAX_SEQUENCE_FRAMES",
    "MIN_PREVIEW_FPS",
    "FrameBudget",
    "measure_actual_fps",
    "resolve_frame_budget",
]
