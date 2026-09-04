import base64
import struct
import zlib
from pathlib import Path

import httpx
import pytest

from backend.schemas import (
    CameraFramingDiagnosticsResult,
    ListSceneCamerasResult,
    SceneCameraInfo,
    VideoFrame,
    VideoFrameSequence,
    VideoFramesResult,
    VideoMp4Result,
    VisualComparisonResult,
    VisualInspectionResult,
)
from backend.tools import vision


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def _no_sleep(_seconds: float) -> None:
    """Stub for vision._sleep so captures and retries run without real delays."""
    return None


class FakeBridge:
    def __init__(self, response: dict[str, object] | list[dict[str, object]]) -> None:
        self.responses = response if isinstance(response, list) else [response]
        self.codes: list[str] = []
        self.native_payloads: list[dict[str, object] | None] = []
        self.play_mode_changes: list[bool] = []
        self.editor_state: dict[str, object] = {"isPlaying": False}
        self.fail_stop_play_mode = False

    async def execute_code(self, code: str) -> dict[str, object]:
        self.codes.append(code)
        return self.responses.pop(0)

    async def render_camera(
        self, code: str, _camera_name: str, _width: int, _height: int, _image_format: str = "PNG"
    ) -> dict[str, object]:
        return await self.execute_code(code)

    async def execute_capability(
        self, code: str, *, native_path: str | None = None, native_payload: dict[str, object] | None = None
    ) -> dict[str, object]:
        del native_path
        self.native_payloads.append(native_payload)
        return await self.execute_code(code)

    async def get_editor_state(self) -> dict[str, object]:
        return self.editor_state

    async def set_play_mode(self, active: bool) -> dict[str, object]:
        if self.fail_stop_play_mode and not active:
            raise RuntimeError("bridge unavailable during play mode restore")
        self.play_mode_changes.append(active)
        self.editor_state = {"isPlaying": active}
        return {"success": True, "isPlaying": active}

    async def wait_for_play_mode(
        self,
        target_playing: bool,
        timeout_seconds: float = 30.0,
        poll_interval_seconds: float = 0.5,
    ) -> dict[str, object]:
        del timeout_seconds, poll_interval_seconds
        if self.fail_stop_play_mode and not target_playing:
            raise RuntimeError("bridge unavailable during play mode restore")
        self.editor_state = {"isPlaying": target_playing, "isCompiling": False, "isUpdating": False}
        return self.editor_state

    async def wait_for_editor_ready(
        self,
        timeout_seconds: float = 15.0,
        poll_interval_seconds: float = 0.5,
    ) -> dict[str, object]:
        del timeout_seconds, poll_interval_seconds
        if self.fail_stop_play_mode:
            raise RuntimeError("bridge unavailable during play mode restore")
        return self.editor_state

    @property
    def code(self) -> str | None:
        return self.codes[-1] if self.codes else None


def _png_base64(
    color: tuple[int, int, int],
    size: tuple[int, int] = (2, 2),
    changed_pixel: tuple[int, int, tuple[int, int, int]] | None = None,
) -> str:
    width, height = size
    rows = []
    for y in range(height):
        row = bytearray([0])
        for x in range(width):
            pixel = color
            if changed_pixel and (x, y) == changed_pixel[:2]:
                pixel = changed_pixel[2]
            row.extend(pixel)
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


@pytest.mark.anyio
async def test_screenshot_returns_unity_camera_capture(monkeypatch: pytest.MonkeyPatch) -> None:
    image_base64 = _png_base64((255, 0, 0), (4, 3))
    fake_bridge = FakeBridge(
        {
            "success": True,
            "result": {
                "imageBase64": image_base64,
                "width": 4,
                "height": 3,
                "cameraName": "Scene Camera",
                "warnings": ["camera disabled"],
            },
        },
    )
    monkeypatch.setattr(vision, "bridge", fake_bridge)

    result = await vision.screenshot(camera_name="Scene Camera", width=4, height=3)

    assert result.success is True
    assert result.error is None
    assert result.image_base64 == image_base64
    assert result.width == 4
    assert result.height == 3
    assert result.camera_name == "Scene Camera"
    assert result.warnings == ["camera disabled"]
    assert fake_bridge.code is not None
    assert "RenderTexture.active" in fake_bridge.code
    assert "targetTexture" in fake_bridge.code


@pytest.mark.anyio
async def test_screenshot_reports_unity_execution_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(vision, "bridge", FakeBridge({"success": False, "error": "Camera not found: Missing"}))

    result = await vision.screenshot(camera_name="Missing", width=16, height=16)

    assert result.success is False
    assert result.error == "Camera not found: Missing"
    assert result.image_base64 is None


@pytest.mark.anyio
async def test_screenshot_rejects_invalid_dimensions() -> None:
    result = await vision.screenshot(width=0, height=16)

    assert result.success is False
    assert result.error == "width and height must be positive integers"


def test_compare_screenshots_reports_changed_area() -> None:
    before = _png_base64((0, 0, 0), (2, 2))
    after = _png_base64((0, 0, 0), (2, 2), changed_pixel=(1, 0, (255, 255, 255)))

    result = vision.compare_screenshots(before_image_base64=before, after_image_base64=after, threshold=1)

    assert isinstance(result, VisualComparisonResult)
    assert result.success is True
    assert result.same_dimensions is True
    assert result.width == 2
    assert result.height == 2
    assert result.changed_pixel_ratio == 0.25
    assert result.changed_bounds == [1, 0, 1, 0]
    assert result.max_delta == 255
    assert result.mean_delta > 0


def test_compare_screenshots_reports_dimension_mismatch() -> None:
    result = vision.compare_screenshots(
        before_image_base64=_png_base64((0, 0, 0), (2, 2)),
        after_image_base64=_png_base64((0, 0, 0), (3, 2)),
    )

    assert result.success is False
    assert result.same_dimensions is False
    assert result.error == "screenshots must have matching dimensions"


def test_camera_screenshot_code_is_valid_inside_bridge_method_wrapper() -> None:
    code = vision._camera_screenshot_code("Main Camera", 640, 360)

    assert "using System;" not in code
    assert "using UnityEngine;" not in code
    assert "System.Convert.ToBase64String" in code
    assert "UnityEngine.RenderTexture.active" in code


@pytest.mark.anyio
async def test_list_scene_cameras_returns_camera_inventory(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_bridge = FakeBridge(
        {
            "success": True,
            "result": {
                "cameras": [
                    {
                        "name": "Main Camera",
                        "path": "Main Camera",
                        "enabled": True,
                        "active": True,
                        "tag": "MainCamera",
                        "depth": 0.0,
                        "fieldOfView": 60.0,
                        "orthographic": False,
                        "orthographicSize": 5.0,
                    },
                ],
            },
        },
    )
    monkeypatch.setattr(vision, "bridge", fake_bridge)

    result = await vision.list_scene_cameras()

    assert isinstance(result, ListSceneCamerasResult)
    assert result.success is True
    assert result.error is None
    assert result.camera_count == 1
    assert len(result.cameras) == 1
    assert isinstance(result.cameras[0], SceneCameraInfo)
    assert result.cameras[0].name == "Main Camera"
    assert result.cameras[0].field_of_view == 60.0
    assert result.cameras[0].orthographic is False
    assert fake_bridge.code is not None
    assert "FindObjectsByType<UnityEngine.Camera>" in fake_bridge.code


@pytest.mark.anyio
async def test_list_scene_cameras_handles_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(vision, "bridge", FakeBridge({"success": False, "error": "Unity execution failed"}))

    result = await vision.list_scene_cameras()

    assert isinstance(result, ListSceneCamerasResult)
    assert result.success is False
    assert result.error == "Unity execution failed"
    assert result.camera_count == 0
    assert result.cameras == []


@pytest.mark.anyio
async def test_project_world_points_returns_viewport_points(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_bridge = FakeBridge(
        {
            "success": True,
            "result": {
                "screenPoints": [
                    {"x": 0.5, "y": 0.5, "z": 3.0, "isBehindCamera": False},
                    {"x": 1.2, "y": 0.4, "z": 2.0, "isBehindCamera": False},
                    {"x": 0.2, "y": 0.2, "z": -1.0, "isBehindCamera": True},
                ],
            },
        },
    )
    monkeypatch.setattr(vision, "bridge", fake_bridge)

    result = await vision.project_world_points([[0, 0, 3], [10, 0, 3], [0, 0, -1]])

    assert result.success is True
    assert [point.is_behind_camera for point in result.screen_points] == [False, False, True]
    assert result.screen_points[1].x == 1.2
    assert fake_bridge.code is not None
    assert "WorldToViewportPoint" in fake_bridge.code


@pytest.mark.anyio
async def test_project_world_points_flattens_points_for_native_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression test: native mode's CameraProjectRequest.points is a flat float[], not
    float[][], because JsonUtility (Unity's own JSON deserializer) can't deserialize jagged
    arrays - verified live that a nested-list payload silently deserializes as points == null.
    Legacy mode is unaffected (points are compiled straight into C# array literals), so only the
    native_payload shape is asserted here.
    """
    fake_bridge = FakeBridge({"success": True, "result": {"screenPoints": []}})
    monkeypatch.setattr(vision, "bridge", fake_bridge)

    await vision.project_world_points([[0, 0, 3], [10, 0, 3], [0, 0, -1]])

    assert fake_bridge.native_payloads[-1] == {
        "cameraName": "Main Camera",
        "points": [0, 0, 3, 10, 0, 3, 0, 0, -1],
    }


@pytest.mark.anyio
async def test_project_world_points_rejects_invalid_points() -> None:
    result = await vision.project_world_points([[0, 1]])

    assert result.success is False
    assert result.error == "each world point must contain exactly 3 coordinates"


@pytest.mark.anyio
async def test_diagnose_camera_framing_reports_centered_subject(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_bridge = FakeBridge(
        {
            "success": True,
            "result": {
                "subjectPath": "Avatar",
                "cameraName": "Main Camera",
                "viewportBounds": [0.25, 0.1, 0.75, 0.9],
                "visibleRatio": 1.0,
                "isVisible": True,
                "isBehindCamera": False,
                "isClipped": False,
                "framingStatus": "centered",
                "warnings": [],
            },
        },
    )
    monkeypatch.setattr(vision, "bridge", fake_bridge)

    result = await vision.diagnose_camera_framing(subject_path="Avatar")

    assert isinstance(result, CameraFramingDiagnosticsResult)
    assert result.success is True
    assert result.subject_path == "Avatar"
    assert result.viewport_bounds == [0.25, 0.1, 0.75, 0.9]
    assert result.visible_ratio == 1.0
    assert result.framing_status == "centered"
    assert fake_bridge.code is not None
    assert "WorldToViewportPoint" in fake_bridge.code
    assert "bounds.Encapsulate" in fake_bridge.code


@pytest.mark.anyio
async def test_diagnose_camera_framing_reports_unity_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(vision, "bridge", FakeBridge({"success": False, "error": "Subject not found: Missing"}))

    result = await vision.diagnose_camera_framing(subject_path="Missing")

    assert result.success is False
    assert result.error == "Subject not found: Missing"
    assert result.is_visible is False


def test_diagnostic_scene_capture_uses_orthographic_bounds_framing() -> None:
    code = vision._diagnostic_scene_capture_code(None, 640, 360)

    assert "diagnosticCamera.orthographic = true" in code
    assert "diagnosticCamera.orthographicSize" in code
    assert "diagnosticCamera.cullingMask = ~0" in code
    assert "HDAdditionalCameraData" in code
    assert "volumeLayerMask" in code
    assert "Visora Diagnostic Key Light" in code
    assert "Visora Diagnostic Fill Light" in code
    assert "RenderSettings.fog = false" in code
    assert "RenderSettings" in code
    assert "DestroyImmediate(diagnosticRoot)" in code


@pytest.mark.anyio
async def test_inspect_scene_visual_returns_raw_and_diagnostic_captures(monkeypatch: pytest.MonkeyPatch) -> None:
    game_image = _png_base64((2, 2, 2), (4, 3))
    diagnostic_image = _png_base64((180, 180, 180), (4, 3))
    fake_bridge = FakeBridge(
        [
            {
                "success": True,
                "result": {
                    "imageBase64": game_image,
                    "width": 4,
                    "height": 3,
                    "cameraName": "Main Camera",
                    "warnings": [],
                },
            },
            {
                "success": True,
                "result": {
                    "imageBase64": diagnostic_image,
                    "width": 4,
                    "height": 3,
                    "cameraName": "Visora Diagnostic Camera",
                    "mode": "diagnostic_lit",
                    "subjectPath": "Avatar",
                    "warnings": ["diagnostic lighting was temporary"],
                },
            },
        ],
    )
    monkeypatch.setattr(vision, "bridge", fake_bridge)

    result = await vision.inspect_scene_visual(subject_path="Avatar", camera_name="Main Camera", width=4, height=3)

    assert isinstance(result, VisualInspectionResult)
    assert result.success is True
    assert result.subject_path == "Avatar"
    assert [capture.mode for capture in result.captures] == ["game_camera", "diagnostic_lit"]
    assert result.captures[0].image_base64 == game_image
    assert result.captures[1].image_base64 == diagnostic_image
    assert result.captures[1].camera_name == "Visora Diagnostic Camera"
    assert any("diagnostic" in warning.lower() for warning in result.warnings)
    assert "Use diagnostic_lit" in result.recommended_interpretation
    assert len(fake_bridge.codes) == 2
    assert "RenderSettings" in fake_bridge.codes[1]
    assert "DestroyImmediate" in fake_bridge.codes[1]


@pytest.mark.anyio
async def test_inspect_scene_visual_keeps_diagnostic_capture_when_game_camera_is_dark(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    diagnostic_image = _png_base64((180, 180, 180), (4, 3))
    fake_bridge = FakeBridge(
        [
            {"success": False, "error": "Camera not found: Main Camera"},
            {
                "success": True,
                "result": {
                    "imageBase64": diagnostic_image,
                    "width": 4,
                    "height": 3,
                    "cameraName": "Visora Diagnostic Camera",
                    "warnings": [],
                },
            },
        ],
    )
    monkeypatch.setattr(vision, "bridge", fake_bridge)

    result = await vision.inspect_scene_visual(width=4, height=3)

    assert result.success is True
    assert [capture.mode for capture in result.captures] == ["diagnostic_lit"]
    assert any("game camera capture failed" in warning.lower() for warning in result.warnings)
    assert "Do not conclude the scene is empty" in result.recommended_interpretation


@pytest.mark.anyio
async def test_get_video_frames_enters_and_restores_play_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    dark_frame = _png_base64((0, 0, 0), (4, 3))
    moving_frame = _png_base64((0, 0, 0), (4, 3), changed_pixel=(1, 1, (255, 255, 255)))
    fake_bridge = FakeBridge(
        [
            {
                "success": True,
                "result": {
                    "imageBase64": dark_frame,
                    "width": 4,
                    "height": 3,
                    "cameraName": "Visora Diagnostic Camera",
                    "warnings": [],
                },
            },
            {
                "success": True,
                "result": {
                    "imageBase64": moving_frame,
                    "width": 4,
                    "height": 3,
                    "cameraName": "Visora Diagnostic Camera",
                    "warnings": [],
                },
            },
            {
                "success": True,
                "result": {
                    "imageBase64": moving_frame,
                    "width": 4,
                    "height": 3,
                    "cameraName": "Visora Diagnostic Camera",
                    "warnings": [],
                },
            },
        ],
    )
    monkeypatch.setattr(vision, "bridge", fake_bridge)

    monkeypatch.setattr(vision, "_sleep", _no_sleep)

    result = await vision.get_video_frames(
        camera_names=["Main Camera"],
        duration_seconds=1.0,
        fps=3,
        width=4,
        height=3,
    )

    assert isinstance(result, VideoFramesResult)
    assert result.success is True
    assert fake_bridge.play_mode_changes == [True, False]
    assert len(result.sequences) == 1
    assert isinstance(result.sequences[0], VideoFrameSequence)
    timestamps = [frame.timestamp_seconds for frame in result.sequences[0].frames]
    assert len(timestamps) == 3
    # Timestamps are measured from the capture clock rather than derived from frame_index / fps, so
    # they only have to start at the capture start and increase; with _sleep stubbed out they are
    # near zero, which is exactly the truth about how fast these frames were really taken.
    assert timestamps == sorted(timestamps)
    assert timestamps[0] >= 0.0
    assert result.sequences[0].timing_source == "python_wallclock"
    assert len(result.sequences[0].motion_metrics) == 2
    assert result.sequences[0].motion_metrics[0].changed_pixel_ratio > 0
    assert result.sequences[0].motion_metrics[1].changed_pixel_ratio == 0
    assert "diagnostic_lit" in result.recommended_interpretation


@pytest.mark.anyio
async def test_get_video_frames_does_not_stop_existing_play_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_bridge = FakeBridge(
        {
            "success": True,
            "result": {
                "imageBase64": _png_base64((0, 0, 0), (2, 2)),
                "width": 2,
                "height": 2,
                "cameraName": "Main Camera",
                "warnings": [],
            },
        },
    )
    fake_bridge.editor_state = {"isPlaying": True}
    monkeypatch.setattr(vision, "bridge", fake_bridge)

    monkeypatch.setattr(vision, "_sleep", _no_sleep)

    result = await vision.get_video_frames(
        camera_names=["Main Camera"],
        mode="game_camera",
        duration_seconds=0.5,
        fps=1,
        width=2,
        height=2,
    )

    assert result.success is True
    assert fake_bridge.play_mode_changes == []


@pytest.mark.anyio
async def test_get_video_frames_rejects_invalid_limits() -> None:
    result = await vision.get_video_frames(duration_seconds=20.0, fps=60, width=4096, height=2160)

    assert result.success is False
    assert "duration_seconds must be between 0.1 and 10.0" in (result.error or "")


@pytest.mark.anyio
async def test_get_video_frames_reports_restore_failure_as_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_bridge = FakeBridge({"success": False, "error": "capture failed"})
    fake_bridge.fail_stop_play_mode = True
    monkeypatch.setattr(vision, "bridge", fake_bridge)

    monkeypatch.setattr(vision, "_sleep", _no_sleep)

    result = await vision.get_video_frames(duration_seconds=0.5, fps=1, width=2, height=2)

    assert result.success is False
    assert any("failed to restore play mode" in warning.lower() for warning in result.warnings)


@pytest.mark.anyio
async def test_get_video_mp4_returns_base64_and_artifact_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    frame = _png_base64((0, 0, 0), (2, 2))
    fake_bridge = FakeBridge(
        [{"success": True, "result": {"imageBase64": frame, "width": 2, "height": 2}} for _ in range(2)]
    )
    monkeypatch.setattr(vision, "bridge", fake_bridge)
    monkeypatch.setattr(vision, "_sleep", _no_sleep)

    encoded_fps: list[float] = []

    def fake_encode(_frames: list[str], fps: float, _width: int, _height: int) -> tuple[bytes, Path]:
        encoded_fps.append(fps)
        path = tmp_path / "visora-video-test.mp4"
        path.write_bytes(b"mp4-bytes")
        return b"mp4-bytes", path

    monkeypatch.setattr(vision, "_encode_frames_to_mp4", fake_encode)

    result = await vision.get_video_mp4(duration_seconds=1.0, fps=2, width=2, height=2)

    assert isinstance(result, VideoMp4Result)
    assert result.success is True
    assert result.video_base64 == base64.b64encode(b"mp4-bytes").decode("ascii")
    assert result.artifact_path is not None
    assert result.artifact_path.endswith("visora-video-test.mp4")
    assert result.format == "mp4"
    # Encoded at the rate the capture achieved, so playback matches real elapsed time.
    assert encoded_fps == [pytest.approx(result.actual_fps or 2.0)]


@pytest.mark.anyio
async def test_get_video_mp4_accepts_fps_above_the_frame_payload_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Regression for #6: get_video_mp4 delegated to get_video_frames, which re-validated with the 12 fps
    payload ceiling, so the MP4 tool rejected its own default fps of 24.
    """
    frame = _png_base64((0, 0, 0), (2, 2))
    fake_bridge = FakeBridge(
        [{"success": True, "result": {"imageBase64": frame, "width": 2, "height": 2}} for _ in range(24)]
    )
    monkeypatch.setattr(vision, "bridge", fake_bridge)
    monkeypatch.setattr(vision, "_sleep", _no_sleep)
    monkeypatch.setattr(
        vision, "_encode_frames_to_mp4", lambda _frames, _fps, _w, _h: (b"mp4-bytes", Path("visora.mp4"))
    )

    result = await vision.get_video_mp4(duration_seconds=1.0, fps=24, width=2, height=2)

    assert result.success is True
    assert result.fps == 24

    # The frame-sequence tool keeps its own lower ceiling, because it returns every frame as base64.
    frames_result = await vision.get_video_frames(duration_seconds=1.0, fps=24, width=2, height=2)
    assert frames_result.success is False
    assert frames_result.error == "fps must be between 1 and 12"


@pytest.mark.anyio
async def test_get_video_mp4_reports_encoder_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    frame = _png_base64((0, 0, 0), (2, 2))
    fake_bridge = FakeBridge([{"success": True, "result": {"imageBase64": frame, "width": 2, "height": 2}}])
    monkeypatch.setattr(vision, "bridge", fake_bridge)
    monkeypatch.setattr(vision, "_sleep", _no_sleep)

    def failing_encode(_frames: list[str], _fps: float, _width: int, _height: int) -> tuple[bytes, Path]:
        raise RuntimeError("ffmpeg unavailable")

    monkeypatch.setattr(vision, "_encode_frames_to_mp4", failing_encode)

    result = await vision.get_video_mp4(duration_seconds=1.0, fps=1, width=2, height=2)

    assert result.success is False
    assert result.error == "ffmpeg unavailable"


@pytest.mark.anyio
async def test_get_video_frames_handles_domain_reload_drop_and_reconnect(monkeypatch: pytest.MonkeyPatch) -> None:
    frame = _png_base64((10, 20, 30), (4, 3))

    class DomainReloadBridge(FakeBridge):
        def __init__(self) -> None:
            super().__init__([{"success": True, "result": {"imageBase64": frame, "width": 4, "height": 3}}])
            self.set_play_mode_called = False
            self.wait_for_play_mode_calls: list[bool] = []

        async def set_play_mode(self, _active: bool) -> dict[str, object]:
            self.set_play_mode_called = True
            # Simulate socket drop / RemoteProtocolError when Unity unloads domain
            raise httpx.RequestError("Connection reset by peer during assembly reload")

        async def wait_for_play_mode(
            self, target_playing: bool, timeout_seconds: float = 30.0, poll_interval_seconds: float = 0.5
        ) -> dict[str, object]:
            del timeout_seconds, poll_interval_seconds
            self.wait_for_play_mode_calls.append(target_playing)
            self.editor_state = {"isPlaying": target_playing, "isCompiling": False, "isUpdating": False}
            return self.editor_state

    reload_bridge = DomainReloadBridge()
    monkeypatch.setattr(vision, "bridge", reload_bridge)
    monkeypatch.setattr(vision, "_sleep", _no_sleep)

    result = await vision.get_video_frames(
        duration_seconds=0.5,
        fps=1,
        width=4,
        height=3,
        enter_play_mode=True,
    )

    assert result.success is True
    assert reload_bridge.set_play_mode_called is True
    assert reload_bridge.wait_for_play_mode_calls == [True, False]
    assert len(result.sequences[0].frames) == 1


@pytest.mark.anyio
async def test_frame_capture_retries_transient_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """A single dropped frame must not end the recording: domain reloads cost one frame, not all of them."""
    frame = _png_base64((10, 20, 30), (2, 2))

    class FlakyBridge(FakeBridge):
        def __init__(self) -> None:
            super().__init__([{"success": True, "result": {"imageBase64": frame, "width": 2, "height": 2}}] * 3)
            self.attempts = 0

        async def execute_code(self, code: str) -> dict[str, object]:
            self.attempts += 1
            if self.attempts == 2:
                raise RuntimeError("bridge dropped mid-capture")
            return await super().execute_code(code)

    flaky = FlakyBridge()
    monkeypatch.setattr(vision, "bridge", flaky)
    monkeypatch.setattr(vision, "_sleep", _no_sleep)

    result = await vision.get_video_frames(duration_seconds=1.0, fps=3, width=2, height=2)

    assert result.success is True
    assert len(result.sequences[0].frames) == 3
    assert [frame.frame_index for frame in result.sequences[0].frames] == [0, 1, 2]


@pytest.mark.anyio
async def test_frame_capture_gives_up_after_repeated_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    frame = _png_base64((10, 20, 30), (2, 2))

    class FailingBridge(FakeBridge):
        def __init__(self) -> None:
            super().__init__([{"success": True, "result": {"imageBase64": frame, "width": 2, "height": 2}}])

        async def execute_code(self, code: str) -> dict[str, object]:
            if self.responses:
                return await super().execute_code(code)
            raise RuntimeError("bridge is gone")

    monkeypatch.setattr(vision, "bridge", FailingBridge())
    monkeypatch.setattr(vision, "_sleep", _no_sleep)

    result = await vision.get_video_frames(duration_seconds=1.0, fps=3, width=2, height=2)

    assert len(result.sequences[0].frames) == 1
    assert any("capture failed after 3 attempts" in warning for warning in result.sequences[0].warnings)


@pytest.mark.anyio
async def test_game_camera_discards_stale_pre_play_mode_frame(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    After entering Play Mode the Game View can still hold the Edit Mode image. Frames matching a
    pre-transition baseline are discarded before the recording starts.
    """
    stale = _png_base64((0, 0, 0), (4, 3))
    live = _png_base64((0, 0, 0), (4, 3), changed_pixel=(1, 1, (255, 255, 255)))

    def payload(image: str) -> dict[str, object]:
        return {"success": True, "result": {"imageBase64": image, "width": 4, "height": 3}}

    # baseline (Edit Mode) -> stale warm-up frame -> live warm-up frame -> two recorded frames
    fake_bridge = FakeBridge([payload(stale), payload(stale), payload(live), payload(live), payload(live)])
    monkeypatch.setattr(vision, "bridge", fake_bridge)
    monkeypatch.setattr(vision, "_sleep", _no_sleep)

    result = await vision.get_video_frames(
        mode="game_camera",
        duration_seconds=1.0,
        fps=2,
        width=4,
        height=3,
    )

    assert result.success is True
    assert len(result.sequences[0].frames) == 2
    assert all(frame.image_base64 == live for frame in result.sequences[0].frames)


@pytest.mark.anyio
async def test_stale_frame_warns_when_view_never_changes(monkeypatch: pytest.MonkeyPatch) -> None:
    """A static scene looks identical to a stale one, so this warns instead of failing."""
    still = _png_base64((0, 0, 0), (4, 3))
    payload = {"success": True, "result": {"imageBase64": still, "width": 4, "height": 3}}

    monkeypatch.setattr(vision, "bridge", FakeBridge([payload] * 6))
    monkeypatch.setattr(vision, "_sleep", _no_sleep)

    result = await vision.get_video_frames(
        mode="game_camera",
        duration_seconds=1.0,
        fps=2,
        width=4,
        height=3,
    )

    assert result.success is True
    assert any("stale" in warning for warning in result.warnings)


@pytest.mark.anyio
async def test_diagnostic_lit_skips_stale_frame_warm_up(monkeypatch: pytest.MonkeyPatch) -> None:
    """diagnostic_lit renders its own camera per frame, so it cannot return pre-Play-Mode content."""
    frame = _png_base64((0, 0, 0), (2, 2))
    fake_bridge = FakeBridge([{"success": True, "result": {"imageBase64": frame, "width": 2, "height": 2}}] * 2)
    monkeypatch.setattr(vision, "bridge", fake_bridge)
    monkeypatch.setattr(vision, "_sleep", _no_sleep)

    result = await vision.get_video_frames(duration_seconds=1.0, fps=2, width=2, height=2)

    assert result.success is True
    # Exactly two captures: no baseline and no warm-up renders were spent.
    assert len(fake_bridge.codes) == 2


class NativeSequenceBridge(FakeBridge):
    """Bridge double advertising Unity-side recording, as the Visora package 1.2.0 does."""

    def __init__(self, payload: dict[str, object], features: set[str] | None = None) -> None:
        super().__init__([])
        self.payload = payload
        self.features = features if features is not None else {"camera_sequence_realtime", "camera_diagnostic_sequence"}
        self.native_sequence_calls: list[dict[str, object]] = []

    async def supports_feature(self, feature: str, force_refresh: bool = False) -> bool:
        del force_refresh
        return feature in self.features

    async def capture_sequence_native(
        self,
        camera_name: str = "Main Camera",
        width: int = 1280,
        height: int = 720,
        frame_count: int = 10,
        interval: float = 0.1,
    ) -> dict[str, object]:
        del width, height
        self.native_sequence_calls.append(
            {"camera": camera_name, "frame_count": frame_count, "interval": interval, "mode": "game_camera"}
        )
        return self.payload

    async def capture_diagnostic_sequence_native(
        self,
        subject_path: str | None = None,
        width: int = 1280,
        height: int = 720,
        frame_count: int = 10,
        interval: float = 0.1,
    ) -> dict[str, object]:
        del width, height
        self.native_sequence_calls.append(
            {"subject": subject_path, "frame_count": frame_count, "interval": interval, "mode": "diagnostic_lit"}
        )
        return self.payload


def _native_payload(frame_images: list[str], actual_fps: float = 9.5) -> dict[str, object]:
    return {
        "success": True,
        "cameraName": "Main Camera",
        "width": 4,
        "height": 3,
        "requestedFps": 24.0,
        "actualFps": actual_fps,
        "timingSource": "native_realtime",
        "totalDuration": 2.3,
        "frames": [
            {"frameIndex": index, "timestamp": index * 0.1, "imageBase64": image}
            for index, image in enumerate(frame_images)
        ],
        "warnings": ["Capture kept up at only 9.5 fps of the requested 24.0 fps"],
    }


@pytest.mark.anyio
async def test_capture_uses_native_recorder_when_advertised(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Unity records the sequence on its own clock in one request. Capturing frame by frame over HTTP
    spends a round trip each time, which caps the real rate far below any requested one.
    """
    first = _png_base64((0, 0, 0), (4, 3))
    second = _png_base64((0, 0, 0), (4, 3), changed_pixel=(1, 1, (255, 255, 255)))
    bridge = NativeSequenceBridge(_native_payload([first, second]))
    monkeypatch.setattr(vision, "bridge", bridge)
    monkeypatch.setattr(vision, "_sleep", _no_sleep)

    result = await vision.get_video_frames(mode="game_camera", duration_seconds=1.0, fps=12, width=4, height=3)

    assert result.success is True
    sequence = result.sequences[0]
    assert sequence.timing_source == "native_realtime"
    assert sequence.actual_fps == pytest.approx(9.5)
    assert [frame.timestamp_seconds for frame in sequence.frames] == [0.0, pytest.approx(0.1)]
    # One request for the whole recording, and no per-frame renders.
    assert len(bridge.native_sequence_calls) == 1
    assert bridge.native_sequence_calls[0]["frame_count"] == 12
    assert bridge.codes == []


@pytest.mark.anyio
async def test_native_recorder_skips_stale_frame_warm_up(monkeypatch: pytest.MonkeyPatch) -> None:
    """The native recorder renders the camera directly, so it cannot return a pre-Play-Mode image."""
    frame = _png_base64((0, 0, 0), (4, 3))
    bridge = NativeSequenceBridge(_native_payload([frame, frame]))
    monkeypatch.setattr(vision, "bridge", bridge)
    monkeypatch.setattr(vision, "_sleep", _no_sleep)

    await vision.get_video_frames(mode="game_camera", duration_seconds=1.0, fps=2, width=4, height=3)

    # No baseline or warm-up renders were spent.
    assert bridge.codes == []


@pytest.mark.anyio
async def test_capture_falls_back_when_bridge_lacks_native_recording(monkeypatch: pytest.MonkeyPatch) -> None:
    """An older Visora package answers the same endpoint with different behaviour, so it is not used."""
    frame = _png_base64((0, 0, 0), (2, 2))
    bridge = NativeSequenceBridge(_native_payload([frame]), features=set())
    bridge.responses = [{"success": True, "result": {"imageBase64": frame, "width": 2, "height": 2}}] * 2
    monkeypatch.setattr(vision, "bridge", bridge)
    monkeypatch.setattr(vision, "_sleep", _no_sleep)

    result = await vision.get_video_frames(duration_seconds=1.0, fps=2, width=2, height=2)

    assert result.success is True
    assert result.sequences[0].timing_source == "python_wallclock"
    assert bridge.native_sequence_calls == []
    assert len(bridge.codes) == 2


@pytest.mark.anyio
async def test_capture_falls_back_when_native_recording_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    frame = _png_base64((0, 0, 0), (2, 2))
    bridge = NativeSequenceBridge({"success": False, "error": "No camera named 'Main Camera' was found"})
    bridge.responses = [{"success": True, "result": {"imageBase64": frame, "width": 2, "height": 2}}] * 2
    monkeypatch.setattr(vision, "bridge", bridge)
    monkeypatch.setattr(vision, "_sleep", _no_sleep)

    result = await vision.get_video_frames(duration_seconds=1.0, fps=2, width=2, height=2)

    assert result.success is True
    assert result.sequences[0].timing_source == "python_wallclock"
    assert any("Native sequence recording was unavailable" in warning for warning in result.warnings)


@pytest.mark.anyio
async def test_repeated_frame_warnings_are_reported_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """A live capture returned the same lighting caveat 24 times, once per frame."""
    frame = _png_base64((0, 0, 0), (2, 2))
    payload = {
        "success": True,
        "result": {"imageBase64": frame, "width": 2, "height": 2, "warnings": ["diagnostic_lit uses temporary camera"]},
    }
    monkeypatch.setattr(vision, "bridge", FakeBridge([payload] * 4))
    monkeypatch.setattr(vision, "_sleep", _no_sleep)

    result = await vision.get_video_frames(duration_seconds=1.0, fps=4, width=2, height=2)

    lighting = [w for w in result.sequences[0].warnings if "temporary camera" in w]
    assert lighting == ["diagnostic_lit uses temporary camera (reported on 4 frames)"]


class AuthoredClipBridge(FakeBridge):
    """Bridge double serving the Edit Mode clip preview endpoint."""

    def __init__(self, payload: dict[str, object], features: set[str] | None = None) -> None:
        super().__init__([])
        self.payload = payload
        self.features = features if features is not None else {"animation_preview_sequence"}
        self.preview_calls: list[dict[str, object]] = []

    async def supports_feature(self, feature: str, force_refresh: bool = False) -> bool:
        del force_refresh
        return feature in self.features

    async def preview_animation_sequence_native(  # noqa: PLR0913
        self,
        camera_name: str,
        clip_path: str,
        target_object_path: str,
        width: int = 640,
        height: int = 360,
        frame_count: int = 24,
        fps: float = 24.0,
        start_time: float = 0.0,
        end_time: float = 0.0,
    ) -> dict[str, object]:
        del width, height, start_time, end_time
        self.preview_calls.append(
            {"camera": camera_name, "clip": clip_path, "target": target_object_path, "frames": frame_count, "fps": fps}
        )
        return self.payload


def _authored_payload(images: list[str], **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "success": True,
        "cameraName": "Main Camera",
        "width": 4,
        "height": 3,
        "actualFps": 24.0,
        "timingSource": "edit_mode_sampled",
        "poseRestored": True,
        "sceneDirtiedByPreview": False,
        "frames": [
            {"frameIndex": index, "timestamp": index / 24, "imageBase64": image} for index, image in enumerate(images)
        ],
        "warnings": [],
    }
    payload.update(overrides)
    return payload


@pytest.mark.anyio
async def test_authored_clip_samples_in_edit_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sampling a clip hits the requested fps exactly and never enters Play Mode."""
    first = _png_base64((0, 0, 0), (4, 3))
    second = _png_base64((0, 0, 0), (4, 3), changed_pixel=(1, 1, (255, 255, 255)))
    bridge = AuthoredClipBridge(_authored_payload([first, second]))
    monkeypatch.setattr(vision, "bridge", bridge)
    monkeypatch.setattr(vision, "_sleep", _no_sleep)

    result = await vision.get_video_frames(
        mode="authored_clip",
        clip_path="Assets/Animations/Punch.anim",
        target_object_path="Fighter",
        duration_seconds=1.0,
        fps=12,
        width=4,
        height=3,
    )

    assert result.success is True
    assert result.sequences[0].timing_source == "edit_mode_sampled"
    assert result.sequences[0].actual_fps == pytest.approx(24.0)
    assert bridge.preview_calls[0]["clip"] == "Assets/Animations/Punch.anim"
    assert bridge.preview_calls[0]["target"] == "Fighter"
    # Edit Mode sampling needs no domain reload.
    assert bridge.play_mode_changes == []


@pytest.mark.anyio
async def test_authored_clip_requires_clip_and_target(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = AuthoredClipBridge(_authored_payload([]))
    monkeypatch.setattr(vision, "bridge", bridge)

    result = await vision.get_video_frames(mode="authored_clip", duration_seconds=1.0, fps=2, width=4, height=3)

    assert result.success is False
    assert result.error is not None
    assert "clip_path and target_object_path" in result.error
    assert bridge.preview_calls == []


@pytest.mark.anyio
async def test_authored_clip_requires_the_native_package(monkeypatch: pytest.MonkeyPatch) -> None:
    """There is no legacy equivalent, so this reports the missing capability instead of falling back."""
    bridge = AuthoredClipBridge(_authored_payload([]), features=set())
    monkeypatch.setattr(vision, "bridge", bridge)

    result = await vision.get_video_frames(
        mode="authored_clip",
        clip_path="Punch",
        target_object_path="Fighter",
        duration_seconds=1.0,
        fps=2,
        width=4,
        height=3,
    )

    assert result.success is False
    assert result.error is not None
    assert "animation_preview_sequence" in result.error
    assert bridge.preview_calls == []


@pytest.mark.anyio
async def test_authored_clip_reports_scene_side_effects(monkeypatch: pytest.MonkeyPatch) -> None:
    frame = _png_base64((0, 0, 0), (4, 3))
    bridge = AuthoredClipBridge(_authored_payload([frame], poseRestored=False, sceneDirtiedByPreview=True))
    monkeypatch.setattr(vision, "bridge", bridge)

    result = await vision.get_video_frames(
        mode="authored_clip",
        clip_path="Punch",
        target_object_path="Fighter",
        duration_seconds=1.0,
        fps=2,
        width=4,
        height=3,
    )

    assert result.success is True
    assert any("pose was restored" in warning for warning in result.warnings)
    assert any("marked the scene as modified" in warning for warning in result.warnings)


@pytest.mark.anyio
async def test_unknown_capture_mode_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(vision, "bridge", FakeBridge([]))

    result = await vision.get_video_frames(mode="cinematic", duration_seconds=1.0, fps=2, width=4, height=3)

    assert result.success is False
    assert result.error == "mode must be diagnostic_lit, game_camera, or authored_clip"
