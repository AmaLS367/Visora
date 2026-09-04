import bisect
from dataclasses import dataclass, field

from backend.tools.animation.preview_math import STATIC_FRAME_RATIO

# Two frames apart, or a tenth of a second, whichever is larger. Below this the images are the same
# picture: an event on the first frame duplicates the boundary, and two events one frame apart give
# an agent two identical pictures for two of its six slots.
_MIN_GAP_FRAMES = 2
_MIN_GAP_SECONDS = 0.1


@dataclass
class KeyFrameChoice:
    """One selected frame, carrying why it was selected."""

    frame_index: int
    source: str
    event_functions: list[str] = field(default_factory=list)


def _nearest_frame(timestamps: list[float], time_seconds: float) -> int:
    position = bisect.bisect_left(timestamps, time_seconds)
    if position == 0:
        return 0
    if position >= len(timestamps):
        return len(timestamps) - 1
    before = timestamps[position - 1]
    after = timestamps[position]
    return position if (after - time_seconds) < (time_seconds - before) else position - 1


def _min_gap(timestamps: list[float]) -> float:
    if len(timestamps) < 2:
        return _MIN_GAP_SECONDS
    duration = timestamps[-1] - timestamps[0]
    step = duration / (len(timestamps) - 1)
    max_allowed = duration * 0.5 if duration > 0 else _MIN_GAP_SECONDS
    return min(max(_MIN_GAP_FRAMES * step, _MIN_GAP_SECONDS), max_allowed)


def _accept(
    candidate: KeyFrameChoice,
    chosen: dict[int, KeyFrameChoice],
    timestamps: list[float],
    min_gap: float,
    budget: int,
) -> bool:
    if len(chosen) >= budget or candidate.frame_index in chosen:
        return False
    candidate_time = timestamps[candidate.frame_index]
    if any(abs(timestamps[index] - candidate_time) < min_gap for index in chosen):
        return False
    chosen[candidate.frame_index] = candidate
    return True


def _thin_evenly(items: list[int], limit: int) -> list[int]:
    """Keeps `limit` entries spread across the list rather than its first `limit`."""
    if limit <= 0 or not items:
        return []
    if len(items) <= limit:
        return items
    step = (len(items) - 1) / (limit - 1) if limit > 1 else 0.0
    return [items[round(position * step)] for position in range(limit)]


def _event_frames(timestamps: list[float], events: list[tuple[float, str]]) -> tuple[list[int], dict[int, list[str]]]:
    """Maps events onto frames, merging every event that lands on the same frame."""
    functions_by_frame: dict[int, list[str]] = {}
    for time_seconds, function_name in sorted(events):
        frame_index = _nearest_frame(timestamps, time_seconds)
        functions_by_frame.setdefault(frame_index, []).append(function_name)
    return sorted(functions_by_frame), functions_by_frame


def _bucketed_peaks(timeline: list[float], buckets: int) -> list[int]:
    """
    Strongest transition per time bucket, strongest bucket first.

    Bucketing is what keeps a mocap take - whose pixel delta peaks dozens of times a second - from
    spending the entire budget inside its first half second.

    Transitions below the static threshold are not peaks at all, and offering them would label
    frames of a motionless clip "motion_peak" - telling an agent something moved there when nothing
    did. A static clip is meant to fall through to the even fill instead.
    """
    if not timeline or buckets <= 0:
        return []
    width = max(1, len(timeline) / buckets)
    best_per_bucket: dict[int, int] = {}
    for index, ratio in enumerate(timeline):
        if ratio < STATIC_FRAME_RATIO:
            continue
        bucket = int(index / width)
        current = best_per_bucket.get(bucket)
        if current is None or ratio > timeline[current]:
            best_per_bucket[bucket] = index
    # Timeline entry i describes the transition into frame i + 1: that is the frame that shows it.
    return [index + 1 for index in sorted(best_per_bucket.values(), key=lambda i: timeline[i], reverse=True)]


def select_key_frames(
    timestamps: list[float],
    timeline: list[float],
    events: list[tuple[float, str]],
    max_key_frames: int,
) -> list[KeyFrameChoice]:
    """
    Picks the frames worth looking at, in a fixed priority order, spread across the clip.

    Order is boundary, then authored event times, then motion peaks, then an even fill. The fill is
    not decoration: an idle or loop clip has no events and no peaks above the static threshold, so
    without it the result is two boundary frames that on a loop look identical - and an agent reads
    that as a character who never moved.
    """
    if not timestamps:
        return []

    budget = max(1, max_key_frames)
    min_gap = _min_gap(timestamps)
    chosen: dict[int, KeyFrameChoice] = {}

    _accept(KeyFrameChoice(0, "boundary"), chosen, timestamps, min_gap, budget)
    if len(timestamps) > 1:
        _accept(KeyFrameChoice(len(timestamps) - 1, "boundary"), chosen, timestamps, min_gap, budget)

    event_frames, functions_by_frame = _event_frames(timestamps, events)
    for frame_index in _thin_evenly(event_frames, budget - len(chosen)):
        _accept(
            KeyFrameChoice(frame_index, "clip_event", list(functions_by_frame[frame_index])),
            chosen,
            timestamps,
            min_gap,
            budget,
        )

    for frame_index in _bucketed_peaks(timeline, budget):
        _accept(KeyFrameChoice(frame_index, "motion_peak"), chosen, timestamps, min_gap, budget)

    if len(chosen) < budget and len(timestamps) > 1:
        slots = budget + 2
        for position in range(1, slots):
            frame_index = round((len(timestamps) - 1) * position / slots)
            _accept(KeyFrameChoice(frame_index, "equidistant"), chosen, timestamps, min_gap, budget)

    return [chosen[index] for index in sorted(chosen)]


__all__ = ["KeyFrameChoice", "select_key_frames"]
