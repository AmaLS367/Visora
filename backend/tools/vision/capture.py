from pathlib import Path
from typing import cast

from mcp.server.mcpserver import Image
from PIL import Image as PILImage

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
    _create_side_by_side_comparison,
    _extract_result_payload,
    _payload_warnings,
    _save_image_artifact,
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
) -> tuple[ScreenshotResult, Image] | ScreenshotResult:
    """
    Captures a high-resolution screenshot from the specified editor or gameplay camera.
    Saves the image to disk as an artifact and returns an Image block for native vision along with metadata.

    Args:
        camera_name: Name of the Unity camera in the active scene to render from.
        width: Desired width of the screenshot in pixels.
        height: Desired height of the screenshot in pixels.

    Returns:
        A tuple of (ScreenshotResult, Image) containing file path, metadata, and native visual content,
        or a ScreenshotResult on failure.
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

        saved_path = _save_image_artifact(image_base64, prefix="screenshot", subfolder="screenshots")
        result = ScreenshotResult(
            success=True,
            file_path=str(saved_path),
            width=int(payload.get("width", width)),
            height=int(payload.get("height", height)),
            camera_name=str(payload.get("cameraName", camera_name)),
            warnings=_payload_warnings(payload),
        )
        return (result, Image(path=saved_path))
    except Exception as exc:
        vision_pkg.logger.exception("Screenshot capture failed")
        return ScreenshotResult(success=False, error=str(exc))


@mcp.tool()
def compare_screenshots(
    before_image_path: str,
    after_image_path: str,
    threshold: int = 8,
) -> tuple[VisualComparisonResult, Image] | VisualComparisonResult:
    """
    Compares two screenshots and returns compact visual-change diagnostics.

    Args:
        before_image_path: Absolute or relative local path to the reference image (or base64 string).
        after_image_path: Absolute or relative local path to the target image (or base64 string).
        threshold: Per-channel delta threshold required to count a pixel as changed.

    Returns:
        A tuple of (VisualComparisonResult, Image) with changed-pixel metrics, bounding box,
        and diff visualization image, or a VisualComparisonResult on failure.
    """
    result, diff_path = compare_images_data(before_image_path, after_image_path, threshold)
    if not result.success:
        return result
    if diff_path is not None:
        return (result, Image(path=diff_path))
    return result


@mcp.tool()
async def inspect_scene_visual(
    subject_path: str | None = None,
    camera_name: str = "Main Camera",
    width: int = 1280,
    height: int = 720,
) -> tuple[VisualInspectionResult, Image] | VisualInspectionResult:
    """
    Captures a scene with both authored camera rendering and diagnostic inspection rendering.
    Combines both perspectives side-by-side into a single comparative image for multimodal vision.

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
    saved_paths: list[Path] = []
    warnings: list[str] = [
        "Use diagnostic_lit for model, pose, rig, and animation inspection when authored lighting is incomplete.",
        "Use game_camera for final player-facing composition only; darkness there is not proof that the subject is missing.",
    ]

    try:
        game_response = await vision_pkg.bridge.render_camera(
            _camera_screenshot_code(camera_name, width, height), camera_name, width, height
        )
        game_payload = _extract_result_payload(game_response)
        capture, path = _capture_from_payload("game_camera", game_payload, camera_name)
        captures.append(capture)
        saved_paths.append(path)
        warnings.extend(f"game_camera: {warning}" for warning in _payload_warnings(game_payload))
    except Exception as exc:
        vision_pkg.logger.warning("Game camera visual inspection capture failed: %s", exc)
        warnings.append(f"game camera capture failed: {exc}")

    try:
        diagnostic_response = await vision_pkg.bridge.execute_capability(
            _diagnostic_scene_capture_code(subject_path, width, height)
        )
        diagnostic_payload = _extract_result_payload(diagnostic_response)
        capture, path = _capture_from_payload("diagnostic_lit", diagnostic_payload, "Visora Diagnostic Camera")
        captures.append(capture)
        saved_paths.append(path)
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

    contact_sheet_path: Path | None = None
    if len(saved_paths) == 2:
        img1 = PILImage.open(saved_paths[0])
        img2 = PILImage.open(saved_paths[1])
        sheet = _create_side_by_side_comparison(img1, img2, "Game Camera", "Diagnostic Lit")
        contact_sheet_path = _save_image_artifact(sheet, prefix="inspection", subfolder="screenshots")
    elif len(saved_paths) == 1:
        contact_sheet_path = saved_paths[0]

    result = VisualInspectionResult(
        success=True,
        subject_path=subject_path,
        contact_sheet_path=str(contact_sheet_path) if contact_sheet_path else None,
        captures=captures,
        warnings=warnings,
        recommended_interpretation=(
            "Use diagnostic_lit first to inspect the actual model, pose, animation, mesh, and silhouette. "
            "Do not conclude the scene is empty, broken, or missing from a dark game_camera capture alone. "
            "Use game_camera only for authored lighting, final composition, and player-facing framing checks."
        ),
    )

    if contact_sheet_path is not None:
        return (result, Image(path=contact_sheet_path))
    return result


__all__ = [
    "compare_screenshots",
    "inspect_scene_visual",
    "screenshot",
]
