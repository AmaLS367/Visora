import base64
import struct
import zlib

import pytest

from backend.schemas import VisualComparisonResult, VisualInspectionResult
from backend.tools import vision


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class FakeBridge:
    def __init__(self, response: dict[str, object] | list[dict[str, object]]) -> None:
        self.responses = response if isinstance(response, list) else [response]
        self.codes: list[str] = []

    async def execute_code(self, code: str) -> dict[str, object]:
        self.codes.append(code)
        return self.responses.pop(0)

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
