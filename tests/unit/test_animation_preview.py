import base64
import struct
import zlib
from pathlib import Path
from typing import Any

import httpx
import pytest

from backend.bridge.client import UnityBridge
from backend.schemas import AnimationPreviewKeyFrame, AnimationPreviewResult
from backend.tools import animation as animation_pkg
from backend.tools import vision as vision_pkg
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


def test_preview_result_defaults_keep_optional_state_unasserted() -> None:
    result = AnimationPreviewResult(
        success=True,
        clip_path="Assets/VisoraAnim/RebeccaDropkick.anim",
        target_object_path="Rebecca",
        camera_name="Main Camera",
        rendered_camera_name="Main Camera",
        recommended_interpretation="x",
    )

    assert result.auto_frame_status == "disabled"
    assert result.preview_camera_destroyed is None
    assert result.key_frames == []
    assert result.motion_timeline == []
    assert result.video_base64 is None


def test_preview_key_frame_holds_every_event_at_one_timestamp() -> None:
    key_frame = AnimationPreviewKeyFrame(
        frame_index=5,
        timestamp_seconds=0.5,
        normalized_time=0.25,
        source="clip_event",
        event_functions=["OnHit", "PlaySound"],
        image_base64="AAA",
        width=640,
        height=360,
    )

    assert key_frame.event_functions == ["OnHit", "PlaySound"]
    assert key_frame.changed_pixel_ratio_from_previous is None


@pytest.mark.anyio
async def test_preview_sequence_sends_auto_frame_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: dict[str, object] = {}

    async def fake_request(_self: object, _method: str, _path: str, **kwargs: object) -> httpx.Response:
        payload = kwargs.get("json")
        if isinstance(payload, dict):
            sent.update(payload)
        return httpx.Response(200, json={"success": True, "frames": []})

    monkeypatch.setattr(UnityBridge, "_request", fake_request)
    client = UnityBridge()

    await client.preview_animation_sequence_native(
        camera_name="Main Camera",
        clip_path="Assets/A.anim",
        target_object_path="Rebecca",
        auto_frame=False,
    )

    assert sent["autoFrame"] is False


def _png_base64(color: tuple[int, int, int], size: tuple[int, int] = (2, 2)) -> str:
    """Minimal valid PNG so motion metrics have real pixels to diff."""
    width, height = size
    rows = []
    for _ in range(height):
        row = bytearray([0])
        for _ in range(width):
            row.extend(color)
        rows.append(bytes(row))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"".join(rows)))
        + chunk(b"IEND", b"")
    )
    return base64.b64encode(png).decode("ascii")


class FakePreviewBridge:
    """Bridge double covering only what preview_animation calls."""

    def __init__(
        self,
        payload: dict[str, Any],
        *,
        clip_length: float = 2.0,
        supports_autoframe: bool = True,
        is_playing: bool = False,
    ) -> None:
        self.payload = payload
        self.clip_length = clip_length
        self.supports_autoframe = supports_autoframe
        self.is_playing = is_playing
        self.preview_calls: list[dict[str, Any]] = []

    async def get_editor_state(self) -> dict[str, Any]:
        return {"isPlaying": self.is_playing}

    async def supports_feature(self, feature: str, force_refresh: bool = False) -> bool:
        del force_refresh
        return feature != "animation_preview_autoframe" or self.supports_autoframe

    async def execute_capability(
        self, code: str, *, native_path: str | None = None, native_payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        del code, native_path, native_payload
        return {
            "result": {
                "success": True,
                "clipName": "RebeccaDropkick",
                "clipPath": "Assets/VisoraAnim/RebeccaDropkick.anim",
                "length": self.clip_length,
                "fps": 30.0,
                "bindings": [],
                "events": [],
            }
        }

    async def preview_animation_sequence_native(self, **kwargs: Any) -> dict[str, Any]:
        self.preview_calls.append(kwargs)
        return self.payload


def _preview_payload(**overrides: Any) -> dict[str, Any]:
    dark = _png_base64((0, 0, 0))
    light = _png_base64((255, 255, 255))
    payload: dict[str, Any] = {
        "success": True,
        "cameraName": "Main Camera",
        "previewCameraUsed": "Main Camera",
        "autoFrameStatus": "not_needed",
        "framingStatusBefore": "visible",
        "poseRestored": True,
        "sceneDirtiedByPreview": False,
        "previewCameraCreated": False,
        "previewCameraDestroyed": False,
        "events": [],
        "isHumanoidClip": False,
        "unresolvedCurvePaths": 0,
        "clipFps": 30.0,
        "loopTime": False,
        "width": 640,
        "height": 360,
        "frames": [
            {"frameIndex": 0, "timestamp": 0.0, "imageBase64": dark},
            {"frameIndex": 1, "timestamp": 0.5, "imageBase64": light},
            {"frameIndex": 2, "timestamp": 1.0, "imageBase64": dark},
        ],
    }
    payload.update(overrides)
    return payload


def _stub_encoder(monkeypatch: pytest.MonkeyPatch, artifact: Path) -> None:
    def fake_encode(_frames: list[str], _fps: float, _width: int, _height: int) -> tuple[bytes, Path]:
        return b"mp4", artifact

    monkeypatch.setattr(vision_pkg, "_encode_frames_to_mp4", fake_encode)


@pytest.mark.anyio
async def test_preview_animation_returns_key_frames_and_artifact_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(animation_pkg, "bridge", FakePreviewBridge(_preview_payload()))
    _stub_encoder(monkeypatch, tmp_path / "preview.mp4")

    result = await animation_pkg.preview_animation(
        target_object_path="Rebecca",
        clip_path="Assets/VisoraAnim/RebeccaDropkick.anim",
    )

    assert result.success is True
    assert result.frame_count == 3
    assert result.key_frames
    assert result.video_artifact_path == str(tmp_path / "preview.mp4")
    assert result.video_base64 is None
    assert result.rendered_camera_name == "Main Camera"
    assert result.preview_camera_destroyed is None


@pytest.mark.anyio
async def test_preview_animation_reports_unsupported_auto_frame(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    bridge = FakePreviewBridge(_preview_payload(), supports_autoframe=False)
    monkeypatch.setattr(animation_pkg, "bridge", bridge)
    _stub_encoder(monkeypatch, tmp_path / "preview.mp4")

    result = await animation_pkg.preview_animation(
        target_object_path="Rebecca", clip_path="Assets/VisoraAnim/RebeccaDropkick.anim"
    )

    assert result.success is True
    assert result.auto_frame_status == "unsupported"
    assert bridge.preview_calls[0]["auto_frame"] is False
    assert any("animation_preview_autoframe" in warning for warning in result.warnings)


@pytest.mark.anyio
async def test_preview_animation_keeps_key_frames_when_mp4_encoding_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(animation_pkg, "bridge", FakePreviewBridge(_preview_payload()))

    def failing_encode(*_args: Any) -> tuple[bytes, Path]:
        raise RuntimeError("ffmpeg missing")

    monkeypatch.setattr(vision_pkg, "_encode_frames_to_mp4", failing_encode)

    result = await animation_pkg.preview_animation(
        target_object_path="Rebecca", clip_path="Assets/VisoraAnim/RebeccaDropkick.anim"
    )

    assert result.success is True
    assert result.video_artifact_path is None
    assert result.key_frames
    assert any("ffmpeg missing" in warning for warning in result.warnings)


@pytest.mark.anyio
async def test_preview_animation_refuses_play_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(animation_pkg, "bridge", FakePreviewBridge(_preview_payload(), is_playing=True))

    result = await animation_pkg.preview_animation(
        target_object_path="Rebecca", clip_path="Assets/VisoraAnim/RebeccaDropkick.anim"
    )

    assert result.success is False
    assert result.error is not None
    assert "game_camera" in result.error


@pytest.mark.anyio
async def test_preview_animation_lowers_fps_for_a_long_clip(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    bridge = FakePreviewBridge(_preview_payload(), clip_length=30.0)
    monkeypatch.setattr(animation_pkg, "bridge", bridge)
    _stub_encoder(monkeypatch, tmp_path / "preview.mp4")

    result = await animation_pkg.preview_animation(
        target_object_path="Rebecca", clip_path="Assets/VisoraAnim/RebeccaDropkick.anim"
    )

    assert result.effective_fps < 24
    assert result.frame_ceiling_applied is True
    assert result.range_truncated is False
    assert result.end_time == 30.0


@pytest.mark.anyio
async def test_preview_animation_surfaces_unrestored_pose(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(animation_pkg, "bridge", FakePreviewBridge(_preview_payload(poseRestored=False)))
    _stub_encoder(monkeypatch, tmp_path / "preview.mp4")

    result = await animation_pkg.preview_animation(
        target_object_path="Rebecca", clip_path="Assets/VisoraAnim/RebeccaDropkick.anim"
    )

    assert result.success is True
    assert result.pose_restored is False
    assert any("pose" in warning.lower() for warning in result.warnings)


@pytest.mark.anyio
async def test_preview_animation_includes_video_bytes_only_when_requested(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(animation_pkg, "bridge", FakePreviewBridge(_preview_payload()))
    _stub_encoder(monkeypatch, tmp_path / "preview.mp4")

    result = await animation_pkg.preview_animation(
        target_object_path="Rebecca",
        clip_path="Assets/VisoraAnim/RebeccaDropkick.anim",
        include_video_base64=True,
    )

    assert result.success is True
    assert result.video_base64 == base64.b64encode(b"mp4").decode("ascii")


@pytest.mark.anyio
async def test_preview_animation_keeps_a_single_key_frame_without_encoding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    image = _png_base64((0, 0, 0))
    monkeypatch.setattr(
        animation_pkg,
        "bridge",
        FakePreviewBridge(_preview_payload(frames=[{"frameIndex": 0, "timestamp": 0.0, "imageBase64": image}])),
    )

    def encoder_must_not_run(*_args: Any) -> tuple[bytes, Path]:
        raise AssertionError("a single frame must not be encoded as MP4")

    monkeypatch.setattr(vision_pkg, "_encode_frames_to_mp4", encoder_must_not_run)

    result = await animation_pkg.preview_animation(
        target_object_path="Rebecca", clip_path="Assets/VisoraAnim/RebeccaDropkick.anim"
    )

    assert result.success is True
    assert result.frame_count == 1
    assert len(result.key_frames) == 1
    assert result.video_artifact_path is None
    assert any("single captured frame" in warning.lower() for warning in result.warnings)


@pytest.mark.anyio
async def test_preview_animation_preserves_an_explicit_zero_length_range(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = FakePreviewBridge(_preview_payload())
    monkeypatch.setattr(animation_pkg, "bridge", bridge)
    monkeypatch.setattr(vision_pkg, "_encode_frames_to_mp4", lambda *_: (b"", Path("preview.mp4")))

    result = await animation_pkg.preview_animation(
        target_object_path="Rebecca",
        clip_path="Assets/VisoraAnim/RebeccaDropkick.anim",
        start_time=0.0,
        end_time=0.0,
    )

    assert result.start_time == 0.0
    assert result.end_time == 0.0
    assert bridge.preview_calls[0]["frame_count"] == 1
    assert bridge.preview_calls[0]["end_time"] == pytest.approx(0.000001)
