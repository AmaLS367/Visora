import base64
import struct
import zlib
from pathlib import Path

import pytest

from backend.schemas import (
    CameraFramingDiagnosticsResult,
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


class FakeBridge:
    def __init__(self, response: dict[str, object] | list[dict[str, object]]) -> None:
        self.responses = response if isinstance(response, list) else [response]
        self.codes: list[str] = []
        self.play_mode_changes: list[bool] = []
        self.editor_state: dict[str, object] = {"isPlaying": False}
        self.fail_stop_play_mode = False

    async def execute_code(self, code: str) -> dict[str, object]:
        self.codes.append(code)
        return self.responses.pop(0)

    async def get_editor_state(self) -> dict[str, object]:
        return self.editor_state

    async def set_play_mode(self, active: bool) -> dict[str, object]:
        if self.fail_stop_play_mode and not active:
            raise RuntimeError("bridge unavailable during play mode restore")
        self.play_mode_changes.append(active)
        self.editor_state = {"isPlaying": active}
        return {"success": True, "isPlaying": active}

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

    assert len(result) == 1
    assert isinstance(result[0], SceneCameraInfo)
    assert result[0].name == "Main Camera"
    assert result[0].field_of_view == 60.0
    assert result[0].orthographic is False
    assert fake_bridge.code is not None
    assert "FindObjectsByType<UnityEngine.Camera>" in fake_bridge.code


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

    async def no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(vision, "_sleep", no_sleep)

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
    assert [frame.timestamp_seconds for frame in result.sequences[0].frames] == [
        0.0,
        pytest.approx(1 / 3),
        pytest.approx(2 / 3),
    ]
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

    async def no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(vision, "_sleep", no_sleep)

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

    async def no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(vision, "_sleep", no_sleep)

    result = await vision.get_video_frames(duration_seconds=0.5, fps=1, width=2, height=2)

    assert result.success is False
    assert any("failed to restore play mode" in warning.lower() for warning in result.warnings)


@pytest.mark.anyio
async def test_get_video_mp4_returns_base64_and_artifact_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    frame = _png_base64((0, 0, 0), (2, 2))
    frames_result = VideoFramesResult(
        success=True,
        sequences=[
            VideoFrameSequence(
                camera_name="Main Camera",
                mode="diagnostic_lit",
                duration_seconds=1.0,
                fps=2,
                frames=[
                    VideoFrame(
                        frame_index=0,
                        timestamp_seconds=0.0,
                        camera_name="Main Camera",
                        mode="diagnostic_lit",
                        image_base64=frame,
                        width=2,
                        height=2,
                        warnings=[],
                    ),
                    VideoFrame(
                        frame_index=1,
                        timestamp_seconds=0.5,
                        camera_name="Main Camera",
                        mode="diagnostic_lit",
                        image_base64=frame,
                        width=2,
                        height=2,
                        warnings=[],
                    ),
                ],
                motion_metrics=[],
                warnings=[],
            ),
        ],
        warnings=[],
        recommended_interpretation="Use video for temporal inspection.",
    )

    async def fake_get_video_frames(**_kwargs: object) -> VideoFramesResult:
        return frames_result

    def fake_encode(_frames: list[str], _fps: int, _width: int, _height: int) -> tuple[bytes, Path]:
        path = tmp_path / "visora-video-test.mp4"
        path.write_bytes(b"mp4-bytes")
        return b"mp4-bytes", path

    monkeypatch.setattr(vision, "get_video_frames", fake_get_video_frames)
    monkeypatch.setattr(vision, "_encode_frames_to_mp4", fake_encode)

    result = await vision.get_video_mp4(duration_seconds=1.0, fps=2, width=2, height=2)

    assert isinstance(result, VideoMp4Result)
    assert result.success is True
    assert result.video_base64 == base64.b64encode(b"mp4-bytes").decode("ascii")
    assert result.artifact_path is not None
    assert result.artifact_path.endswith("visora-video-test.mp4")
    assert result.format == "mp4"


@pytest.mark.anyio
async def test_get_video_mp4_reports_encoder_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    frame = _png_base64((0, 0, 0), (2, 2))
    frames_result = VideoFramesResult(
        success=True,
        sequences=[
            VideoFrameSequence(
                camera_name="Main Camera",
                mode="diagnostic_lit",
                duration_seconds=1.0,
                fps=1,
                frames=[
                    VideoFrame(
                        frame_index=0,
                        timestamp_seconds=0.0,
                        camera_name="Main Camera",
                        mode="diagnostic_lit",
                        image_base64=frame,
                        width=2,
                        height=2,
                        warnings=[],
                    ),
                ],
                motion_metrics=[],
                warnings=[],
            ),
        ],
        warnings=[],
        recommended_interpretation="Use video for temporal inspection.",
    )

    async def fake_get_video_frames(**_kwargs: object) -> VideoFramesResult:
        return frames_result

    def failing_encode(_frames: list[str], _fps: int, _width: int, _height: int) -> tuple[bytes, Path]:
        raise RuntimeError("ffmpeg unavailable")

    monkeypatch.setattr(vision, "get_video_frames", fake_get_video_frames)
    monkeypatch.setattr(vision, "_encode_frames_to_mp4", failing_encode)

    result = await vision.get_video_mp4(duration_seconds=1.0, fps=1, width=2, height=2)

    assert result.success is False
    assert result.error == "ffmpeg unavailable"
