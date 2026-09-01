from typing import cast

import backend.tools.vision as vision_pkg
from backend.app import mcp
from backend.schemas import (
    ScreenshotResult,
    VisualCapture,
    VisualComparisonResult,
    VisualInspectionResult,
)
from backend.tools.vision.image_utils import (
    _capture_from_payload,
    _extract_result_payload,
    _payload_warnings,
    compare_images_data,
)
from backend.tools.vision.scripts import (
    _camera_screenshot_code,
    _diagnostic_scene_capture_code,
)


@mcp.tool()
async def screenshot(
    camera_name: str = "Main Camera",
    width: int = 1920,
    height: int = 1080,
) -> ScreenshotResult:
    """
    Captures a high-resolution screenshot from the specified editor or gameplay camera.

    Args:
        camera_name: Name of the Unity camera in the active scene to render from.
        width: Desired width of the screenshot in pixels.
        height: Desired height of the screenshot in pixels.

    Returns:
        A ScreenshotResult object containing base64-encoded image data or error details.
    """
    if width <= 0 or height <= 0:
        return ScreenshotResult(success=False, error="width and height must be positive integers")

    try:
        response = await vision_pkg.bridge.render_camera(
            _camera_screenshot_code(camera_name, width, height), camera_name, width, height
        )
        payload = _extract_result_payload(response)
        if not payload.get("success", True) or payload.get("error"):
            return ScreenshotResult(
                success=False,
                error=str(payload.get("error", "Unity screenshot capture failed")),
                camera_name=camera_name,
                warnings=_payload_warnings(payload),
            )

        image_base64 = payload.get("imageBase64") or payload.get("image_base64")
        if not isinstance(image_base64, str) or not image_base64:
            return ScreenshotResult(
                success=False,
                error="Unity screenshot response did not include imageBase64",
                camera_name=camera_name,
                warnings=_payload_warnings(payload),
            )

        return ScreenshotResult(
            success=True,
            image_base64=image_base64,
            width=int(payload.get("width", width)),
            height=int(payload.get("height", height)),
            camera_name=str(payload.get("cameraName", camera_name)),
            warnings=_payload_warnings(payload),
        )
    except Exception as exc:
        vision_pkg.logger.exception("Screenshot capture failed")
        return ScreenshotResult(success=False, error=str(exc))


@mcp.tool()
def compare_screenshots(
    before_image_base64: str,
    after_image_base64: str,
    threshold: int = 8,
) -> VisualComparisonResult:
    """
    Compares two screenshots and returns compact visual-change diagnostics.

    Args:
        before_image_base64: Base64 encoded PNG/JPEG image before a scene change.
        after_image_base64: Base64 encoded PNG/JPEG image after a scene change.
        threshold: Per-channel delta threshold required to count a pixel as changed.

    Returns:
        A VisualComparisonResult with changed-pixel metrics and changed bounds.
    """
    return compare_images_data(before_image_base64, after_image_base64, threshold)


@mcp.tool()
async def inspect_scene_visual(
    subject_path: str | None = None,
    camera_name: str = "Main Camera",
    width: int = 1280,
    height: int = 720,
) -> VisualInspectionResult:
    """
    Captures a scene with both authored camera rendering and diagnostic inspection rendering.

    Use this when the user asks what is visible in a Unity scene, whether a model/pose/animation looks correct,
    or when production lighting, environment, or final camera framing may be incomplete. Agents should inspect
    diagnostic_lit for model and animation visibility before drawing conclusions from game_camera darkness.
    """
    if width <= 0 or height <= 0:
        return VisualInspectionResult(
            success=False,
            error="width and height must be positive integers",
            subject_path=subject_path,
            recommended_interpretation="No captures were produced because the requested dimensions were invalid.",
        )

    captures: list[VisualCapture] = []
    warnings: list[str] = [
        "Use diagnostic_lit for model, pose, rig, and animation inspection when authored lighting is incomplete.",
        "Use game_camera for final player-facing composition only; darkness there is not proof that the subject is missing.",
    ]

    try:
        game_response = await vision_pkg.bridge.render_camera(
            _camera_screenshot_code(camera_name, width, height), camera_name, width, height
        )
        game_payload = _extract_result_payload(game_response)
        captures.append(_capture_from_payload("game_camera", game_payload, camera_name))
        warnings.extend(f"game_camera: {warning}" for warning in _payload_warnings(game_payload))
    except Exception as exc:
        vision_pkg.logger.warning("Game camera visual inspection capture failed: %s", exc)
        warnings.append(f"game camera capture failed: {exc}")

    try:
        diagnostic_response = await vision_pkg.bridge.execute_code(
            _diagnostic_scene_capture_code(subject_path, width, height)
        )
        diagnostic_payload = _extract_result_payload(diagnostic_response)
        captures.append(_capture_from_payload("diagnostic_lit", diagnostic_payload, "Visora Diagnostic Camera"))
        warnings.extend(f"diagnostic_lit: {warning}" for warning in _payload_warnings(diagnostic_payload))
    except Exception as exc:
        vision_pkg.logger.exception("Diagnostic visual inspection capture failed")
        warnings.append(f"diagnostic capture failed: {exc}")

    if not captures:
        return VisualInspectionResult(
            success=False,
            error="all visual inspection captures failed",
            subject_path=subject_path,
            captures=[],
            warnings=warnings,
            recommended_interpretation=(
                "No visual capture was available. Check Unity bridge status, scene renderers, and camera names before "
                "making visual conclusions."
            ),
        )

    return VisualInspectionResult(
        success=True,
        subject_path=subject_path,
        captures=captures,
        warnings=warnings,
        recommended_interpretation=(
            "Use diagnostic_lit first to inspect the actual model, pose, animation, mesh, and silhouette. "
            "Do not conclude the scene is empty, broken, or missing from a dark game_camera capture alone. "
            "Use game_camera only for authored lighting, final composition, and player-facing framing checks."
        ),
    )


__all__ = [
    "compare_screenshots",
    "inspect_scene_visual",
    "screenshot",
]
