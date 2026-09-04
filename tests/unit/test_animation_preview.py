import pytest

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
