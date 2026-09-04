import pytest

from backend.tools.animation.preview_keyframes import select_key_frames
from backend.tools.animation.preview_math import (
    MAX_SEQUENCE_FRAMES,
    measure_actual_fps,
    resolve_frame_budget,
    summarize_motion,
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def test_frame_budget_keeps_requested_fps_when_it_fits() -> None:
    budget = resolve_frame_budget(start_time=0.0, end_time=2.0, requested_fps=24)

    assert budget.effective_fps == 24.0
    assert budget.frame_count == 49
    assert budget.frame_ceiling_applied is False
    assert budget.range_truncated is False


def test_frame_budget_lowers_fps_instead_of_cutting_the_range() -> None:
    budget = resolve_frame_budget(start_time=0.0, end_time=30.0, requested_fps=24)

    assert budget.end_time == 30.0
    assert budget.range_truncated is False
    assert budget.frame_ceiling_applied is True
    assert budget.effective_fps <= (MAX_SEQUENCE_FRAMES - 1) / 30.0
    assert budget.frame_count <= MAX_SEQUENCE_FRAMES


def test_frame_budget_truncates_only_past_the_one_fps_floor() -> None:
    budget = resolve_frame_budget(start_time=0.0, end_time=400.0, requested_fps=24)

    assert budget.effective_fps == 1.0
    assert budget.range_truncated is True
    assert budget.end_time == pytest.approx(239.0)
    assert budget.frame_count == MAX_SEQUENCE_FRAMES


def test_frame_budget_returns_one_frame_for_an_empty_range() -> None:
    budget = resolve_frame_budget(start_time=1.5, end_time=1.5, requested_fps=24)

    assert budget.frame_count == 1
    assert budget.end_time == 1.5


def test_measure_actual_fps_uses_timestamps_not_the_requested_range() -> None:
    assert measure_actual_fps([0.0, 0.5, 1.0]) == pytest.approx(2.0)


def test_measure_actual_fps_is_none_without_two_distinct_timestamps() -> None:
    assert measure_actual_fps([0.25]) is None
    assert measure_actual_fps([]) is None
    assert measure_actual_fps([1.0, 1.0]) is None


def test_summarize_motion_locates_the_peak_at_the_later_frame_of_the_pair() -> None:
    summary = summarize_motion(timeline=[0.01, 0.40, 0.02], timestamps=[0.0, 0.1, 0.2, 0.3])

    assert summary.peak_changed_pixel_ratio == 0.40
    assert summary.peak_motion_timestamp == 0.2
    assert summary.is_static is False


def test_summarize_motion_reports_a_static_clip() -> None:
    summary = summarize_motion(timeline=[0.0, 0.0, 0.0], timestamps=[0.0, 0.1, 0.2, 0.3])

    assert summary.is_static is True
    assert summary.peak_motion_timestamp is None
    assert summary.static_intervals == [(0.0, 0.3)]


def test_summarize_motion_reports_a_hold_inside_a_moving_clip() -> None:
    summary = summarize_motion(
        timeline=[0.5, 0.0, 0.0, 0.5],
        timestamps=[0.0, 0.1, 0.2, 0.3, 0.4],
    )

    assert summary.is_static is False
    assert summary.static_intervals == [(0.1, 0.3)]


def test_summarize_motion_handles_a_single_frame() -> None:
    summary = summarize_motion(timeline=[], timestamps=[0.0])

    assert summary.is_static is True
    assert summary.peak_changed_pixel_ratio == 0.0
    assert summary.static_intervals == []


def _even_timestamps(count: int, fps: float = 10.0) -> list[float]:
    return [index / fps for index in range(count)]


def test_key_frames_always_include_both_boundaries() -> None:
    chosen = select_key_frames(
        timestamps=_even_timestamps(20),
        timeline=[0.0] * 19,
        events=[],
        max_key_frames=6,
    )

    assert chosen[0].frame_index == 0
    assert chosen[0].source == "boundary"
    assert chosen[-1].frame_index == 19
    assert chosen[-1].source == "boundary"


def test_key_frames_fill_a_static_loop_clip_with_equidistant_frames() -> None:
    chosen = select_key_frames(
        timestamps=_even_timestamps(20),
        timeline=[0.0] * 19,
        events=[],
        max_key_frames=6,
    )

    assert len(chosen) == 6
    assert {choice.source for choice in chosen} == {"boundary", "equidistant"}


def test_key_frames_prefer_clip_events_over_motion_peaks() -> None:
    timeline = [0.0] * 19
    timeline[15] = 0.9

    chosen = select_key_frames(
        timestamps=_even_timestamps(20),
        timeline=timeline,
        events=[(0.5, "OnHit")],
        max_key_frames=3,
    )

    sources = [choice.source for choice in chosen]
    assert sources.count("clip_event") == 1
    assert "motion_peak" not in sources
    event_choice = next(choice for choice in chosen if choice.source == "clip_event")
    assert event_choice.frame_index == 5
    assert event_choice.event_functions == ["OnHit"]


def test_key_frames_merge_several_events_sharing_one_timestamp() -> None:
    chosen = select_key_frames(
        timestamps=_even_timestamps(20),
        timeline=[0.0] * 19,
        events=[(0.5, "OnHit"), (0.5, "PlaySound")],
        max_key_frames=6,
    )

    event_choices = [choice for choice in chosen if choice.source == "clip_event"]
    assert len(event_choices) == 1
    assert event_choices[0].event_functions == ["OnHit", "PlaySound"]


def test_key_frames_drop_an_event_that_collides_with_a_boundary() -> None:
    chosen = select_key_frames(
        timestamps=_even_timestamps(20),
        timeline=[0.0] * 19,
        events=[(0.0, "OnStart")],
        max_key_frames=6,
    )

    assert [choice.frame_index for choice in chosen] == sorted({choice.frame_index for choice in chosen})
    assert chosen[0].frame_index == 0
    assert chosen[0].source == "boundary"


def test_key_frames_spread_mocap_peaks_across_the_clip() -> None:
    # A mocap take peaks on nearly every frame; naive local maxima would spend the whole
    # budget inside the first half second.
    timeline = [0.5 + (0.01 if index % 2 else 0.0) for index in range(39)]

    chosen = select_key_frames(
        timestamps=_even_timestamps(40),
        timeline=timeline,
        events=[],
        max_key_frames=6,
    )

    assert len(chosen) == 6
    indices = [choice.frame_index for choice in chosen]
    assert indices == sorted(indices)
    assert max(indices) - min(indices) > 20


def test_key_frames_never_exceed_the_budget() -> None:
    chosen = select_key_frames(
        timestamps=_even_timestamps(40),
        timeline=[0.4] * 39,
        events=[(float(index) / 10.0, f"Event{index}") for index in range(1, 30)],
        max_key_frames=4,
    )

    assert len(chosen) == 4


def test_key_frames_handle_a_single_frame_clip() -> None:
    chosen = select_key_frames(timestamps=[0.0], timeline=[], events=[], max_key_frames=6)

    assert len(chosen) == 1
    assert chosen[0].frame_index == 0
