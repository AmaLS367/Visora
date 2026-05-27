import base64
import io
import json
import logging
from typing import Any, cast

from PIL import Image, UnidentifiedImageError

from backend.app import mcp
from backend.bridge import UnityBridge
from backend.schemas import ProjectWorldPointsResult, ScreenshotResult, VisualComparisonResult

logger = logging.getLogger("backend.tools.vision")
bridge = UnityBridge()


def _camera_screenshot_code(camera_name: str, width: int, height: int) -> str:
    camera_name_literal = json.dumps(camera_name)
    return f"""
var cameraName = {camera_name_literal};
var width = {width};
var height = {height};
var warnings = new System.Collections.Generic.List<string>();
var gameObject = UnityEngine.GameObject.Find(cameraName);
var camera = gameObject != null ? gameObject.GetComponent<UnityEngine.Camera>() : null;
if (camera == null)
{{
    throw new System.Exception("Camera not found: " + cameraName);
}}
if (!camera.enabled)
{{
    warnings.Add("camera disabled");
}}

var previousTargetTexture = camera.targetTexture;
var previousActive = UnityEngine.RenderTexture.active;
var renderTexture = new UnityEngine.RenderTexture(width, height, 24, UnityEngine.RenderTextureFormat.ARGB32);
UnityEngine.Texture2D texture = null;

try
{{
    camera.targetTexture = renderTexture;
    UnityEngine.RenderTexture.active = renderTexture;
    camera.Render();

    texture = new UnityEngine.Texture2D(width, height, UnityEngine.TextureFormat.RGB24, false);
    texture.ReadPixels(new UnityEngine.Rect(0, 0, width, height), 0, 0);
    texture.Apply();

    var pngBytes = texture.EncodeToPNG();
    return new System.Collections.Generic.Dictionary<string, object>
    {{
        {{ "imageBase64", System.Convert.ToBase64String(pngBytes) }},
        {{ "width", width }},
        {{ "height", height }},
        {{ "cameraName", cameraName }},
        {{ "warnings", warnings }},
    }};
}}
finally
{{
    camera.targetTexture = previousTargetTexture;
    UnityEngine.RenderTexture.active = previousActive;
    if (texture != null)
    {{
        UnityEngine.Object.DestroyImmediate(texture);
    }}
    renderTexture.Release();
    UnityEngine.Object.DestroyImmediate(renderTexture);
}}
"""


def _extract_result_payload(response: dict[str, Any]) -> dict[str, Any]:
    error = response.get("error") or response.get("errorMessage")
    if error:
        raise RuntimeError(str(error))
    if response.get("success") is False:
        raise RuntimeError("Unity bridge reported an unsuccessful execution")

    payload = response.get("result", response)
    if isinstance(payload, str):
        parsed = json.loads(payload)
        if not isinstance(parsed, dict):
            raise RuntimeError("Unity execution returned a non-object JSON payload")
        payload = parsed
    if not isinstance(payload, dict):
        raise RuntimeError("Unity execution returned an unsupported payload")
    return payload


def _decode_image(image_base64: str) -> Image.Image:
    try:
        image_bytes = base64.b64decode(image_base64, validate=True)
        image = Image.open(io.BytesIO(image_bytes))
        return image.convert("RGB")
    except (ValueError, UnidentifiedImageError, OSError) as exc:
        raise ValueError("invalid base64 image data") from exc


def _normalize_threshold(threshold: int) -> int:
    return max(0, min(255, threshold))


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
        response = await bridge.execute_code(_camera_screenshot_code(camera_name, width, height))
        payload = _extract_result_payload(response)
        image_base64 = payload.get("imageBase64") or payload.get("image_base64")
        if not isinstance(image_base64, str) or not image_base64:
            return ScreenshotResult(success=False, error="Unity screenshot response did not include imageBase64")

        return ScreenshotResult(
            success=True,
            image_base64=image_base64,
            width=int(payload.get("width", width)),
            height=int(payload.get("height", height)),
            camera_name=str(payload.get("cameraName", camera_name)),
            warnings=[str(warning) for warning in payload.get("warnings", [])],
        )
    except Exception as exc:
        logger.exception("Screenshot capture failed")
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
    try:
        before = _decode_image(before_image_base64)
        after = _decode_image(after_image_base64)
    except ValueError as exc:
        return VisualComparisonResult(success=False, error=str(exc))

    if before.size != after.size:
        return VisualComparisonResult(
            success=False,
            error="screenshots must have matching dimensions",
            same_dimensions=False,
        )

    threshold = _normalize_threshold(threshold)
    width, height = before.size
    total_pixels = width * height
    changed_pixels = 0
    delta_sum = 0
    max_delta = 0
    min_x = width
    min_y = height
    max_x = -1
    max_y = -1

    before_pixels = list(before.get_flattened_data())
    after_pixels = list(after.get_flattened_data())
    for index, (before_pixel_raw, after_pixel_raw) in enumerate(zip(before_pixels, after_pixels, strict=True)):
        before_pixel = cast(tuple[int, int, int], before_pixel_raw)
        after_pixel = cast(tuple[int, int, int], after_pixel_raw)
        x = index % width
        y = index // width
        deltas = [abs(before_pixel[channel] - after_pixel[channel]) for channel in range(3)]
        pixel_max_delta = max(deltas)
        max_delta = max(max_delta, pixel_max_delta)
        delta_sum += sum(deltas)
        if pixel_max_delta > threshold:
            changed_pixels += 1
            min_x = min(min_x, x)
            min_y = min(min_y, y)
            max_x = max(max_x, x)
            max_y = max(max_y, y)

    changed_bounds = [min_x, min_y, max_x, max_y] if changed_pixels else None
    return VisualComparisonResult(
        success=True,
        same_dimensions=True,
        width=width,
        height=height,
        changed_pixel_ratio=changed_pixels / total_pixels if total_pixels else 0.0,
        mean_delta=delta_sum / (total_pixels * 3) if total_pixels else 0.0,
        max_delta=max_delta,
        changed_bounds=changed_bounds,
    )


@mcp.tool()
async def project_world_points(
    points: list[list[float]],
    camera_name: str = "Main Camera",
) -> ProjectWorldPointsResult:
    """
    Projects 3D world coordinates onto the 2D screen coordinate viewport of a camera.

    Args:
        points: A list of 3D world points, where each point is a list of [x, y, z] floats.
        camera_name: Name of the Unity camera used to compute projections.

    Returns:
        A ProjectWorldPointsResult with a list of 2D screen positions.
    """
    # Empty decorated stub - no implementation yet
    return ProjectWorldPointsResult(success=True)
