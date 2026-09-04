import math
from dataclasses import dataclass
from itertools import pairwise

from backend.tools.vision import _motion_metric_from_frames

# Mirrors CameraRenderingService.MaxSequenceFrames: every frame is held in memory as a base64 PNG
# until the whole sequence is serialized, so this bounds the response size, not the clip length.
MAX_SEQUENCE_FRAMES = 240

# Below this the preview stops being a preview, so the range is shortened instead of sampling slower.
MIN_PREVIEW_FPS = 1.0

# Below this changed-pixel ratio two frames are treated as showing the same thing. Matches the
# threshold the video capture core already uses, so "static" means the same thing across tools.
STATIC_FRAME_RATIO = 0.001


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


@dataclass(frozen=True)
class MotionSummaryData:
    """Compact description of where a clip moves and where it holds still."""

    peak_motion_timestamp: float | None
    peak_changed_pixel_ratio: float
    mean_changed_pixel_ratio: float
    static_intervals: list[tuple[float, float]]
    is_static: bool


def build_motion_timeline(frame_images_base64: list[str]) -> list[float]:
    """Changed-pixel ratio for every adjacent frame pair - the whole motion profile as plain floats."""
    return [
        _motion_metric_from_frames(
            from_frame=index,
            to_frame=index + 1,
            before_base64=before,
            after_base64=after,
        ).changed_pixel_ratio
        for index, (before, after) in enumerate(pairwise(frame_images_base64))
    ]


def summarize_motion(timeline: list[float], timestamps: list[float]) -> MotionSummaryData:
    """
    Reduces the timeline to the few facts an agent acts on: when it peaks, and where it holds.

    Each timeline entry describes the transition into a frame, so a peak is reported at the later
    frame's timestamp - that is the frame showing the changed pose.
    """
    if not timeline:
        return MotionSummaryData(
            peak_motion_timestamp=None,
            peak_changed_pixel_ratio=0.0,
            mean_changed_pixel_ratio=0.0,
            static_intervals=[],
            is_static=True,
        )

    peak_ratio = max(timeline)
    is_static = peak_ratio < STATIC_FRAME_RATIO
    peak_index = timeline.index(peak_ratio)

    intervals: list[tuple[float, float]] = []
    run_start: int | None = None
    for index, ratio in enumerate(timeline):
        if ratio < STATIC_FRAME_RATIO:
            if run_start is None:
                run_start = index
        elif run_start is not None:
            intervals.append((timestamps[run_start], timestamps[index]))
            run_start = None
    if run_start is not None:
        intervals.append((timestamps[run_start], timestamps[-1]))

    return MotionSummaryData(
        peak_motion_timestamp=None if is_static else timestamps[peak_index + 1],
        peak_changed_pixel_ratio=peak_ratio,
        mean_changed_pixel_ratio=sum(timeline) / len(timeline),
        static_intervals=intervals,
        is_static=is_static,
    )


__all__ = [
    "MAX_SEQUENCE_FRAMES",
    "MIN_PREVIEW_FPS",
    "STATIC_FRAME_RATIO",
    "FrameBudget",
    "MotionSummaryData",
    "build_motion_timeline",
    "measure_actual_fps",
    "resolve_frame_budget",
    "summarize_motion",
]
